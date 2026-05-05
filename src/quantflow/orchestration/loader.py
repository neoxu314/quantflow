"""Task Configuration Loader."""
import yaml
from pathlib import Path

class TaskConfig:
    def __init__(self, name, watchlist_path, strategy_names, days_back=None):
        self.name = name
        self.watchlist_path = watchlist_path
        self.strategy_names = strategy_names
        self.days_back = days_back

    @staticmethod
    def load(file_path: str):
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {file_path}")
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        tasks = []
        names_seen = set()
        for item in data.get('tasks', []):
            name = item['name']
            if name in names_seen:
                raise ValueError(
                    f"Duplicate task name '{name}' in config file. "
                    "Each task must have a unique name."
                )
            names_seen.add(name)
            tasks.append(TaskConfig(
                name=name,
                watchlist_path=item['watchlist'],
                strategy_names=item.get('strategies', []),
                days_back=item.get('days_back')
            ))
        return tasks