import json
from typing import Optional, Dict, Any
from app.core.interfaces.llm_interface import LLMInterface


class MockLLM(LLMInterface):
    """
    Mock LLM for testing and development.
    Returns a structurally valid StructuredLLMOutput JSON response.
    """

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        # Extract fault code from prompt for a slightly realistic mock
        fault_code = "UNKNOWN"
        for line in prompt.split("\n"):
            if "Code:" in line:
                fault_code = line.split("Code:")[-1].strip()
                break

        response = {
            "summary": (
                f"Fault '{fault_code}' has been detected. Based on the provided statistics, "
                "this fault exhibits a pattern consistent with intermittent hardware or communication issues. "
                "Review the diagnostic steps and consult documentation for resolution."
            ),
            "likely_causes": [
                "Sensor or actuator threshold exceeded during normal operation cycle",
                "Communication timeout between PLC and field device",
                "Power supply instability causing intermittent resets",
            ],
            "diagnostic_steps": [
                "Verify power supply voltage at the device terminals (should be within ±5% of rated)",
                "Check network cable integrity and connector seating on Profibus/Profinet node",
                "Review PLC I/O module status LEDs for error indication",
                "Monitor fault frequency over the next hour to detect burst patterns",
            ],
            "preventive_actions": [
                "Schedule preventive maintenance for sensor calibration",
                "Add surge protection on supply rails if not present",
                "Review alarm hysteresis settings to avoid nuisance trips",
            ],
            "related_plc_tags": [],
            "confidence_explanation": (
                "Confidence is determined by occurrence frequency and burst detection — "
                "see statistics panel for exact thresholds applied."
            ),
        }
        return json.dumps(response)

    def generate_json(self, prompt: str, schema: Any, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        return json.loads(self.generate(prompt, system_prompt))
