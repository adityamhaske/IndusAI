from app.evaluation.golden_dataset_runner import GoldenDatasetRunner
from app.services.chat_service import ChatService

class EvaluationService:
    def __init__(self, chat_service: ChatService, golden_dataset_path: str):
        self.runner = GoldenDatasetRunner(chat_service, golden_dataset_path)

    def run_full_evaluation(self):
        return self.runner.run_evaluation()
