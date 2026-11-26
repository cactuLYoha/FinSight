
"""Read-only PDF analysis; never creates ledger entries."""
import json
from functools import partial

from bankstatementparser.hybrid import smart_ingest
from bankstatementparser.hybrid.llm_extractor import LLMExtractor, LLMExtractorError
from bankstatementparser.hybrid.ollama_direct import ollama_direct_completion
from bankstatementparser.hybrid.pdf_text import PDFExtractionError
from pypdf import PdfReader
from pypdf.errors import PdfReadError


class StatementError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def analyze_statement(path, *, model='ollama/qwen2.5:3b', api_base=None):
    if not model.startswith('ollama/'):
        raise StatementError('Configure a local Ollama model for statement analysis.', 503)
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise StatementError('Upload a PDF without password protection.')
        if not 1 <= len(reader.pages) <= 20:
            raise StatementError('Upload a statement containing 1–20 pages.')
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        if len(text.strip()) < 50:
            raise StatementError('This PDF has no readable text. Upload a digital statement instead of a scan.')
    except StatementError:
        raise
    except (PdfReadError, ValueError, KeyError, OSError) as error:
        raise StatementError('The PDF could not be read. Try another bank export.') from error
    extractor = LLMExtractor(model=model, api_base=api_base,
                             completion_fn=partial(ollama_direct_completion, timeout=180))
    try:
        result = smart_ingest(path, extractor=extractor)
    except LLMExtractorError as error:
        raise StatementError('Analysis is unavailable. Check that Ollama is running and the configured model is installed.', 503) from error
    except PDFExtractionError as error:
        raise StatementError('The PDF could not be analyzed. Try another bank export.') from error
    payload = json.loads(result.to_json())
    fields = ('amount', 'currency', 'booking_date', 'value_date', 'description', 'confidence')
    return {'source_method': payload['source_method'], 'verification': payload['verification'],
            'transactions': [{key: row.get(key) for key in fields} for row in payload['transactions']]}
