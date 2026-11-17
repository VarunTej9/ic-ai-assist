import logging
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .repository import SyntheticModelRepository
from .schemas import (
    ApiErrorResponse,
    ApiResponse,
    AskQuestionRequest,
    AssistantAnswerResponse,
    DemoTokenRequest,
    DemoTokenResponse,
    FeedbackRequest,
    FeedbackResponse,
    ModelAnomaliesResponse,
    ModelHistoryResponse,
)
from .security import (
    CurrentUser,
    create_access_token,
    feedback_access,
    read_access,
    settings,
)
from .services import (
    AssistantService,
    DownstreamServiceError,
    FeedbackService,
    InvestigationService,
    LocalRagBackend,
    ModelNotFoundError,
    RecommendationNotFoundError,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ic_ai_assist.story5")

def create_app() -> FastAPI:
    app = FastAPI(
        title="IC AI Assist Investigation API",
        version="1.0.0",
        description="Read-only API using synthetic project data.",
    )

    repository = SyntheticModelRepository()
    app.state.repository = repository

    app.state.investigation_service = InvestigationService(repository)
    app.state.assistant_service = AssistantService(
        repository,
        LocalRagBackend(),
    )
    app.state.feedback_service = FeedbackService(repository)

    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):
        supplied_id = request.headers.get("X-Correlation-ID")

        try:
            correlation_id = (
                str(uuid.UUID(supplied_id))
                if supplied_id
                else str(uuid.uuid4())
            )
        except ValueError:
            correlation_id = str(uuid.uuid4())

        request.state.correlation_id = correlation_id
        started = time.perf_counter()

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id

        logger.info(
            "%s %s status=%s duration_ms=%.2f correlation_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
            correlation_id,
        )

        return response

    def error_response(
        request: Request,
        status_code: int,
        code: str,
        message: str,
    ) -> JSONResponse:
        body = ApiErrorResponse(
            code=code,
            message=message,
            correlation_id=request.state.correlation_id,
        )

        return JSONResponse(
            status_code=status_code,
            content=body.model_dump(mode="json"),
            headers={
                "X-Correlation-ID": request.state.correlation_id
            },
        )

    @app.exception_handler(ModelNotFoundError)
    async def model_not_found(request: Request, _: Exception):
        return error_response(
            request, 404, "MODEL_NOT_FOUND",
            "The requested model was not found.",
        )

    @app.exception_handler(RecommendationNotFoundError)
    async def recommendation_not_found(request: Request, _: Exception):
        return error_response(
            request, 404, "RECOMMENDATION_NOT_FOUND",
            "The requested recommendation was not found.",
        )

    @app.exception_handler(DownstreamServiceError)
    async def downstream_error(request: Request, _: Exception):
        return error_response(
            request, 503, "DOWNSTREAM_SERVICE_UNAVAILABLE",
            "The assistant service is temporarily unavailable.",
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = {
            401: "AUTHENTICATION_REQUIRED",
            403: "FORBIDDEN",
        }.get(exc.status_code, "REQUEST_ERROR")

        return error_response(
            request,
            exc.status_code,
            code,
            str(exc.detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request,
        _: RequestValidationError,
    ):
        return error_response(
            request, 422, "VALIDATION_ERROR",
            "The request did not match the API contract.",
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.exception("Unhandled API error")
        return error_response(
            request, 500, "INTERNAL_ERROR",
            "An unexpected error occurred.",
        )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post(
        "/api/v1/auth/demo-token",
        response_model=ApiResponse[DemoTokenResponse],
        tags=["Authentication"],
    )
    async def create_demo_token(
        request: Request,
        payload: DemoTokenRequest,
    ):
        if settings.app_environment not in {"development", "test"}:
            raise HTTPException(status_code=404, detail="Not found.")

        token = create_access_token(
            payload.user_id,
            payload.tenant_id,
            payload.role,
        )

        return ApiResponse(
            data=DemoTokenResponse(
                access_token=token,
                expires_in_seconds=(
                    settings.jwt_expiration_minutes * 60
                ),
            ),
            correlation_id=request.state.correlation_id,
        )

    @app.get(
        "/api/v1/models/{model_id}/history",
        response_model=ApiResponse[ModelHistoryResponse],
        tags=["Investigation"],
    )
    async def get_history(
        model_id: str,
        request: Request,
        user: CurrentUser = Depends(read_access),
    ):
        data = app.state.investigation_service.get_history(
            model_id,
            user.tenant_id,
        )
        return ApiResponse(
            data=data,
            correlation_id=request.state.correlation_id,
        )

    @app.get(
        "/api/v1/models/{model_id}/anomalies",
        response_model=ApiResponse[ModelAnomaliesResponse],
        tags=["Investigation"],
    )
    async def get_anomalies(
        model_id: str,
        request: Request,
        user: CurrentUser = Depends(read_access),
    ):
        data = app.state.investigation_service.get_anomalies(
            model_id,
            user.tenant_id,
        )
        return ApiResponse(
            data=data,
            correlation_id=request.state.correlation_id,
        )

    @app.post(
        "/api/v1/assistant/questions",
        response_model=ApiResponse[AssistantAnswerResponse],
        tags=["Assistant"],
    )
    async def ask_question(
        payload: AskQuestionRequest,
        request: Request,
        user: CurrentUser = Depends(read_access),
    ):
        data = app.state.assistant_service.ask(
            payload,
            user.tenant_id,
        )
        return ApiResponse(
            data=data,
            correlation_id=request.state.correlation_id,
        )

    @app.post(
        "/api/v1/recommendations/{recommendation_id}/feedback",
        response_model=ApiResponse[FeedbackResponse],
        tags=["Feedback"],
    )
    async def add_feedback(
        recommendation_id: str,
        payload: FeedbackRequest,
        request: Request,
        user: CurrentUser = Depends(feedback_access),
    ):
        data = app.state.feedback_service.add_feedback(
            recommendation_id,
            payload,
            user.user_id,
            user.tenant_id,
        )
        return ApiResponse(
            data=data,
            correlation_id=request.state.correlation_id,
        )

    return app

app = create_app()
