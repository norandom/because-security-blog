"""
Functional programming types and utilities for Nuitka compilation
"""
from typing import Union, Generic, TypeVar, Callable, List, Optional, Any, Dict
from dataclasses import dataclass
from pathlib import Path
import asyncio
from functools import reduce
from datetime import datetime, timezone
import re

T = TypeVar('T')
U = TypeVar('U')
E = TypeVar('E')

# Result type for functional error handling
@dataclass
class Success(Generic[T]):
    """Represents a successful computation"""
    value: T
    
    def is_success(self) -> bool:
        return True
    
    def is_failure(self) -> bool:
        return False

@dataclass
class Failure(Generic[E]):
    """Represents a failed computation"""
    error: E
    
    def is_success(self) -> bool:
        return False
    
    def is_failure(self) -> bool:
        return True

Result = Union[Success[T], Failure[E]]

# Error types
@dataclass
class ParseError:
    message: str
    file_path: Optional[Path] = None
    exception: Optional[Exception] = None

@dataclass
class ValidationError:
    field: str
    message: str

# Functional operators
def map_result(f: Callable[[T], U]) -> Callable[[Result[T, E]], Result[U, E]]:
    """Map function over successful results"""
    def mapper(result: Result[T, E]) -> Result[U, E]:
        match result:
            case Success(value):
                try:
                    return Success(f(value))
                except Exception as e:
                    return Failure(ParseError(f"Map function failed: {e}", exception=e))
            case Failure(error):
                return Failure(error)
    return mapper

def flat_map(f: Callable[[T], Result[U, E]]) -> Callable[[Result[T, E]], Result[U, E]]:
    """Monadic bind for results"""
    def binder(result: Result[T, E]) -> Result[U, E]:
        match result:
            case Success(value):
                try:
                    return f(value)
                except Exception as e:
                    return Failure(ParseError(f"Flat map function failed: {e}", exception=e))
            case Failure(error):
                return Failure(error)
    return binder

def filter_result(predicate: Callable[[T], bool], error_msg: str = "Filter failed") -> Callable[[Result[T, E]], Result[T, E]]:
    """Filter results based on predicate"""
    def filterer(result: Result[T, E]) -> Result[T, E]:
        match result:
            case Success(value):
                return result if predicate(value) else Failure(ValidationError("filter", error_msg))
            case Failure(error):
                return result
    return filterer

# Pipeline composition
class Pipeline:
    """Functional pipeline for chaining operations"""
    def __init__(self, value: Any):
        self.value = value
    
    def pipe(self, func: Callable[[Any], Any]) -> 'Pipeline':
        """Apply function to the current value"""
        try:
            return Pipeline(func(self.value))
        except Exception as e:
            return Pipeline(Failure(ParseError(f"Pipeline error: {e}", exception=e)))
    
    def unwrap(self) -> Any:
        """Extract the final value"""
        return self.value

def pipe(value: Any) -> Pipeline:
    """Start a functional pipeline"""
    return Pipeline(value)

# Async result operations
async def collect_results_async(results: List[Result[T, E]]) -> Result[List[T], List[E]]:
    """Collect async results, separating successes and failures"""
    successes = []
    failures = []
    
    for result in results:
        match result:
            case Success(value):
                successes.append(value)
            case Failure(error):
                failures.append(error)
    
    return Success(successes) if not failures else Failure(failures)

async def sequence_async(computations: List[Callable[[], Result[T, E]]]) -> Result[List[T], E]:
    """Execute computations concurrently and collect results"""
    async def run_computation(comp: Callable[[], Result[T, E]]) -> Result[T, E]:
        return await asyncio.to_thread(comp)
    
    tasks = [run_computation(comp) for comp in computations]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successes = []
    for result in results:
        if isinstance(result, Exception):
            return Failure(ParseError(f"Async computation failed: {result}", exception=result))
        match result:
            case Success(value):
                successes.append(value)
            case Failure(error):
                return Failure(error)
    
    return Success(successes)

# Functional utilities for blog processing
def safe_get(dictionary: Dict[str, Any], key: str, default: Any = None) -> Any:
    """Safely get value from dictionary"""
    return dictionary.get(key, default)

def safe_parse_date(date_input: Any) -> Result[datetime, ParseError]:
    """Safely parse date from various formats"""
    if isinstance(date_input, datetime):
        return Success(date_input.replace(tzinfo=timezone.utc) if date_input.tzinfo is None else date_input)
    
    if isinstance(date_input, str):
        try:
            # Try ISO format first
            date = datetime.fromisoformat(date_input.replace('Z', '+00:00'))
            return Success(date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date)
        except ValueError:
            try:
                # Try other common formats
                for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%B %d, %Y']:
                    try:
                        parsed_date = datetime.strptime(date_input, fmt)
                        return Success(parsed_date.replace(tzinfo=timezone.utc))
                    except ValueError:
                        continue
            except Exception as e:
                return Failure(ParseError(f"Failed to parse date '{date_input}': {e}"))
    
    return Failure(ParseError(f"Invalid date format: {date_input}"))

def safe_parse_tags(tags_input: Any) -> List[str]:
    """Safely parse tags from various formats"""
    if isinstance(tags_input, list):
        return [str(tag).strip() for tag in tags_input if str(tag).strip()]
    elif isinstance(tags_input, str):
        return [tag.strip() for tag in tags_input.split(',') if tag.strip()]
    else:
        return []

def calculate_reading_time_pure(content: str) -> int:
    """Pure function to calculate reading time"""
    # Remove markdown and HTML
    plain_text = re.sub(r'<[^>]+>', '', content)
    plain_text = re.sub(r'[#*`_\[\]()]+', '', plain_text)
    
    # Count words
    words = len(plain_text.split())
    
    # Average reading speed: 200 words per minute
    return max(1, round(words / 200))

def create_excerpt_pure(content: str, max_length: int = 200) -> str:
    """Pure function to create excerpt from content"""
    # Remove markdown formatting
    plain_text = re.sub(r'[#*`_\[\]()]+', '', content)
    plain_text = re.sub(r'\s+', ' ', plain_text).strip()
    
    if len(plain_text) <= max_length:
        return plain_text
    
    # Find last space before max_length to avoid cutting words
    truncated = plain_text[:max_length]
    last_space = truncated.rfind(' ')
    
    if last_space > max_length * 0.8:  # If last space is reasonably close
        return truncated[:last_space] + '...'
    else:
        return truncated + '...'

# Curried functions for composition
def map_list(f: Callable[[T], U]) -> Callable[[List[T]], List[U]]:
    """Curried map for lists"""
    return lambda lst: [f(item) for item in lst]

def filter_list(predicate: Callable[[T], bool]) -> Callable[[List[T]], List[T]]:
    """Curried filter for lists"""
    return lambda lst: [item for item in lst if predicate(item)]

def sort_list(key_func: Callable[[T], Any], reverse: bool = False) -> Callable[[List[T]], List[T]]:
    """Curried sort for lists"""
    return lambda lst: sorted(lst, key=key_func, reverse=reverse)

def take(n: int) -> Callable[[List[T]], List[T]]:
    """Take first n items from list"""
    return lambda lst: lst[:n]

def compose(*functions: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Compose multiple functions right to left"""
    return lambda x: reduce(lambda acc, f: f(acc), reversed(functions), x)