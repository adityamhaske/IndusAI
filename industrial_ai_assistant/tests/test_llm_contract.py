import pytest
from app.llm.mock_llm import MockLLM
from app.core.schemas import ChatResponse

def test_mock_llm_generation():
    llm = MockLLM()
    response = llm.generate("Hello")
    assert isinstance(response, str)
    assert len(response) > 0

def test_mock_llm_json_generation():
    llm = MockLLM()
    response = llm.generate_json("Hello", ChatResponse)
    assert isinstance(response, dict)
    assert "summary" in response
