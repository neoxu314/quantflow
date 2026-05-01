"""Task Configuration Loader."""
import yaml
from pathlib import Path

class TaskConfig:
    def __init__(self, name, watchlist_path, strategy_names, output_dir, days_back=None):
        self.name = name
        self.watchlist_path = watchlist_path
        self.strategy_names = strategy_names
        self.output_dir = output_dir
        self.days_back = days_back

    @staticmethod
    def load(file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {file_path}")
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        tasks = []
        for item in data.get('tasks', []):
            tasks.append(TaskConfig(
                name=item['name'],
                watchlist_path=item['watchlist'],
                strategy_names=item.get('strategies', []),
                output_dir=item.get('output', './output'),
                days_back=item.get('days_back')
            ))
        return tasks