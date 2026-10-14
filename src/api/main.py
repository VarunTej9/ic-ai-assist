from __future__ import annotations

import logging
import time
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .models import (
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
from .repository import SyntheticModelRepository
from .security import (
    AuthUser,
    create_access_token,
    feedback_access,
    get_current_user,
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

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s %(levelname)s "
        "correlation_id=%(correlation_id)s "
        "%(message)s"
    ),
)

logger = logging.getLogger("ic_ai_assist.story5")

def create_app() -> FastAPI:
    app = FastAPI(
        title="IC AI Assist Investigation API",
        version="1.0.0",
        description=(
            "Read-only synthetic investigation API for Story 5."
        ),
    )

    app.state.repository = SyntheticModelRepository()

    app.state.investigation_service = InvestigationService(
        app.state.repository
    )

    app.state.assistant_service = AssistantService(
        repository=app.state.repository,
        rag_backend=LocalRagBackend(),
    )

    app.state.feedback_service = FeedbackService(
        app.state.repository
    )

    @app.middleware("http")
    async def correlation_middleware(
        request: Request,
        call_next,
    ):
        supplied_id = request.headers.get("X-Correlation-ID")

        try:
            correlation_id = str(
                uuid.UUID(supplied_id)
            ) if supplied_id else str(uuid.uuid4())
        except ValueError:
            correlation_id = str(uuid.uuid4())

        request.state.correlation_id = correlation_id

        started = time.perf_counter()

        response = await call_next(request)

        duration_ms = round(
            (time.perf_counter() - started) * 1000,
            2,
        )

        response.headers["X-Correlation-ID"] = correlation_id

        logger.info(
            "%s %s status=%s duration_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={"correlation_id": correlation_id},
        )

        return response

    @app.exception_handler(ModelNotFoundError)
    async def model_not_found_handler(
        request: Request,
        _: ModelNotFoundError,
    ):
        return _error_response(
            request=request,
            status_code=404,
            code="MODEL_NOT_FOUND",
            message="The requested model was not found.",
        )

    @app.exception_handler(RecommendationNotFoundError)
    async def recommendation_not_found_handler(
        request: Request,
        _: RecommendationNotFoundError,
    ):
        return _error_response(
            request=request,
            status_code=404,
            code="RECOMMENDATION_NOT_FOUND",
            message="The requested recommendation was not found.",
        )

    @app.exception_handler(DownstreamServiceError)
    async def downstream_error_handler(
        request: Request,
        _: DownstreamServiceError,
    ):
        return _error_response(
            request=request,
            status_code=503,
            code="DOWNSTREAM_SERVICE_UNAVAILABLE",
            message=(
                "The assistant service is temporarily unavailable."
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exception: HTTPException,
    ):
        if exception.status_code == 401:
            code = "AUTHENTICATION_REQUIRED"
        elif exception.status_code == 403:
            code = "FORBIDDEN"
        else:
            code = "REQUEST_ERROR"

        return _error_response(
            request=request,
            status_code=exception.status_code,
            code=code,
            message=str(exception.detail),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exception: Exception,
    ):
        logger.exception(
            "Unhandled application error",
            exc_info=exception,
            extra={
                "correlation_id": request.state.correlation_id
            },
        )

        return _error_response(
            request=request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/v1/auth/demo-token",
        response_model=ApiResponse[DemoTokenResponse],
        tags=["Authentication"],
    )
    async def demo_token(
        request: Request,
        payload: DemoTokenRequest,
    ):
        if settings.app_environment not in {
            "development",
            "test",
        }:
            raise HTTPException(
                status_code=404,
                detail="Not found.",
            )

        token = create_access_token(
            user_id=payload.user_id,
            tenant_id=payload.tenant_id,
            role=payload.role,
        )

        data = DemoTokenResponse(
            access_token=token,
            expires_in_seconds=(
                settings.jwt_expiration_minutes * 60
            ),
        )

        return _success_response(request, data)

    @app.get(
        "/api/v1/models/{model_id}/history",
        response_model=ApiResponse[ModelHistoryResponse],
        tags=["Investigation"],
    )
    async def get_history(
        model_id: str,
        request: Request,
        user: Annotated[AuthUser, Depends(read_access)],
    ):
        data = app.state.investigation_service.get_history(
            model_id=model_id,
            tenant_id=user.tenant_id,
        )

        return _success_response(request, data)

    @app.get(
        "/api/v1/models/{model_id}/anomalies",
        response_model=ApiResponse[ModelAnomaliesResponse],
        tags=["Investigation"],
    )
    async def get_anomalies(
        model_id: str,
        request: Request,
        user: Annotated[AuthUser, Depends(read_access)],
    ):
        data = app.state.investigation_service.get_anomalies(
            model_id=model_id,
            tenant_id=user.tenant_id,
        )

        return _success_response(request, data)

    @app.post(
        "/api/v1/assistant/questions",
        response_model=ApiResponse[AssistantAnswerResponse],
        tags=["Assistant"],
    )
    async def ask_question(
        payload: AskQuestionRequest,
        request: Request,
        user: Annotated[AuthUser, Depends(read_access)],
    ):
        data = app.state.assistant_service.ask(
            request=payload,
            tenant_id=user.tenant_id,
        )

        return _success_response(request, data)

    @app.post(
        "/api/v1/recommendations/{recommendation_id}/feedback",
        response_model=ApiResponse[FeedbackResponse],
        tags=["Feedback"],
    )
    async def add_feedback(
        recommendation_id: str,
        payload: FeedbackRequest,
        request: Request,
        user: Annotated[
            AuthUser,
            Depends(feedback_access),
        ],
    ):
        data = app.state.feedback_service.add_feedback(
            recommendation_id=recommendation_id,
            request=payload,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
        )

        return _success_response(request, data)

    return app

def _success_response(request: Request, data):
    return ApiResponse(
        data=data,
        correlation_id=request.state.correlation_id,
    )

def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
):
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

app = create_app()
