import json
import traceback
from app.services.query_classifier import classify
from app.models.project_models import (
    IntentType,
    FaultAnalysisResponseModel,
    FileExplanationResponseModel,
    GeneralQueryResponseModel,
)

print("--- Testing Classifier Hierarchy ---")
queries = [
    ("Explain ISO_IO_List.txt", IntentType.FILE_EXPLANATION.value),
    ("Why is ALM_3021 triggered?", IntentType.FAULT_ANALYSIS.value),
    ("What is the flow of the main routine?", IntentType.SYSTEM_FLOW.value),
    ("What is a PLC tag?", IntentType.GENERAL_QUERY.value),
]

for q, expected in queries:
    intent = classify(q)
    print(f"Query: '{q}'\n -> Got: {intent.intent_type}, Expected: {expected}\n")
    assert intent.intent_type == expected, f"Failed: {intent.intent_type} != {expected}"

print("--- Testing Pydantic Validation Fallback ---")
invalid_json = {
    "missing_summary": "Oops",
    "confidence": "HIGH"
}
try:
    model = FileExplanationResponseModel(**invalid_json)
    print("Failed: Should have raised validation error")
except Exception as e:
    print("Passed: Validation failed as expected for invalid payload.")

valid_general = {
    "explanation": "This is a general query.",
    "supporting_sources": ["sourceA"],
    "confidence": "HIGH"
}
model = GeneralQueryResponseModel(**valid_general)
print("Passed: Valid general model constructed.")

print("All backend tests ran successfully.")
