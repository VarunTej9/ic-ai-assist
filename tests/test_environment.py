import pandas
import numpy
import sklearn
import streamlit
import pydantic

def test_required_packages_are_available():
    assert pandas is not None
    assert numpy is not None
    assert sklearn is not None
    assert streamlit is not None
    assert pydantic is not None
