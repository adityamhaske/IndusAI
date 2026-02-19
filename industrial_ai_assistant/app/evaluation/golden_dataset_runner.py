import json
from typing import List, Dict, Any
from app.services.chat_service import ChatService
from app.core.schemas import ChatRequest
from app.evaluation.metrics_calculator import MetricsCalculator

class GoldenDatasetRunner:
    def __init__(self, chat_service: ChatService, dataset_path: str):
        self.chat_service = chat_service
        self.dataset_path = dataset_path
        self.calculator = MetricsCalculator()

    def load_dataset(self) -> List[Dict[str, Any]]:
        with open(self.dataset_path, 'r') as f:
            return json.load(f)

    def run_evaluation(self) -> Dict[str, Any]:
        data = self.load_dataset()
        results = []
        total_metrics = {"tag_recall": 0.0, "citation_recall": 0.0}
        
        print(f"Running evaluation on {len(data)} items...")
        
        for item in data:
            query = item["query"]
            ground_truth = item["expected_response"]
            
            # Run pipeline
            request = ChatRequest(query=query)
            response = self.chat_service.chat(request)
            
            # Calculate metrics
            item_metrics = self.calculator.calculate(response, ground_truth)
            
            # Accumulate
            for k, v in item_metrics.items():
                total_metrics[k] = total_metrics.get(k, 0.0) + v
                
            results.append({
                "id": item["id"],
                "query": query,
                "metrics": item_metrics,
                "response_summary": response.summary
            })
            
        # Average
        if data:
            for k in total_metrics:
                total_metrics[k] /= len(data)
                
        return {
            "summary_metrics": total_metrics,
            "details": results
        }
