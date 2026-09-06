"""
Base Extractor Interface for Knowledge Ingestion Factory.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from src.brain.models.file_metadata import ExtractionResult

class BaseExtractor(ABC):
    @abstractmethod
    def can_handle(self, extension: str, mime_type: str) -> bool:
        """Determines if this extractor supports the given file extension or MIME."""
        pass

    @abstractmethod
    def extract(self, file_path: Path, source_id: str, derived_dir: Path) -> ExtractionResult:
        """Extracts structured elements, text, and metadata from the given source file."""
        pass
