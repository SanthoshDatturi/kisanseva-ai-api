import re
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


def get_validated_model_from_text(text: str, model: Type[T]) -> T | None:
    """
    Extracts a JSON string from a text that may contain Markdown code blocks
    or other surrounding text.

    This function first tries to find a JSON string enclosed in Markdown
    ```json ... ``` blocks. If that fails, it looks for the largest
    JSON object or array. The extracted string is then validated against the
    provided Pydantic model.

    Args:
        text: The input string which may contain an embedded JSON string.
        model: The Pydantic BaseModel class to validate the JSON against.

    Returns:
        An instance of the Pydantic model if a valid JSON string is found.

    Raises:
        ValidationError: If the extracted JSON string does not match the model.
    """
    json_string = None

    # 1. Primary Method: Look for a ```json ... ``` block
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.DOTALL)
    if match:
        json_string = match.group(1).strip()
    else:
        # 2. Fallback Method: Look for the outermost '{...}' or '[...]'
        start_brace = text.find("{")
        start_bracket = text.find("[")

        if start_brace == -1 and start_bracket == -1:
            return None  # No JSON structure found

        start_index = -1
        if start_brace != -1 and start_bracket != -1:
            start_index = min(start_brace, start_bracket)
        elif start_brace != -1:
            start_index = start_brace
        else:
            start_index = start_bracket

        end_char = "}" if text[start_index] == "{" else "]"
        end_index = text.rfind(end_char)

        if end_index > start_index:
            json_string = text[start_index : end_index + 1]

    if json_string:
        try:
            return model.model_validate_json(json_string)
        except ValidationError as e:
            raise e

    raise ValidationError(f"Could not extract valid JSON for model {model.__name__}")
