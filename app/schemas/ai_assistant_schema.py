from pydantic import BaseModel, Field


class AIAssistantQueryRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    project_id: int | None = None
    # Which page/module the widget was opened from (e.g. "bugs", "tasks",
    # "sprints", "reports", "projects", "dashboard"). Optional — the
    # dedicated /ai-assistant page sends none. Lets the assistant tailor
    # generic prompts like "summarize this" to whatever the user is
    # actually looking at instead of only reacting to keywords.
    module: str | None = None


class AIAssistantQueryResponse(BaseModel):
    answer: str
    intent: str
