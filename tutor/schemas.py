"""The shared format for model responses, interview notes, and the PDF."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field, model_validator


SCORING_RUBRIC = (
    ("preparedness", "Preparation demonstrated", 3),
    ("concept_knowledge", "Concept knowledge", 3),
    ("application", "Scenario application", 2),
    ("reasoning", "Reasoning and clarity", 2),
)


class InterviewQuestion(BaseModel):
    model_config = {"extra": "forbid"}
    category: Literal["preparedness", "concept_knowledge", "application", "reasoning"]
    text: str = Field(min_length=5, max_length=400)


class InterviewPlan(BaseModel):
    model_config = {"extra": "forbid"}
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=800)
    questions: list[InterviewQuestion] = Field(max_length=12)
    research_query: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_questions(self):
        if self.research_query is not None:
            if not self.research_query.strip() or self.questions:
                raise ValueError("Request research before supplying interview questions.")
            return self
        if len(self.questions) < 10:
            raise ValueError("The interview plan is incomplete.")
        questions = [" ".join(q.text.split()).casefold() for q in self.questions]
        if len(set(questions)) != len(questions) or any(len(q) < 5 for q in questions):
            raise ValueError("Interview questions must be nonblank and distinct.")
        if {q.category for q in self.questions} != {field for field, _, _ in SCORING_RUBRIC}:
            raise ValueError("Interview questions must cover all four assessment categories.")
        return self


class CriterionScore(BaseModel):
    model_config = {"extra": "forbid"}
    marks: int | None = Field(ge=0, le=3, strict=True)
    reason: str = Field(min_length=1, max_length=400)
    evidence: str = Field(max_length=240)


class InterviewAssessment(BaseModel):
    model_config = {"extra": "forbid"}
    preparedness: CriterionScore
    concept_knowledge: CriterionScore
    application: CriterionScore
    reasoning: CriterionScore
    improvements: list[str] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_marks(self):
        for field, _, maximum in SCORING_RUBRIC:
            item = getattr(self, field)
            if item.marks is not None and item.marks > maximum:
                raise ValueError(f"{field} marks exceed {maximum}.")
        return self

    @property
    def total(self) -> int | None:
        marks = [getattr(self, field).marks for field, _, _ in SCORING_RUBRIC]
        return None if any(mark is None for mark in marks) else sum(marks)

    def validate_evidence(self, answers: list[str]) -> None:
        for field, _, _ in SCORING_RUBRIC:
            item = getattr(self, field)
            if item.marks is not None:
                quote = item.evidence.strip()
                if not quote or not any(quote in answer for answer in answers):
                    raise ValueError("Score evidence does not match the learner's own answers.")


class Approach(BaseModel):
    name: str
    intuition: str
    code: str
    correctness: str
    time_complexity: str
    space_complexity: str
    worked_example: str


class FollowUp(BaseModel):
    question: str
    sketch: str


class StudyNotes(BaseModel):
    summary: str
    assumptions: list[str]
    key_concepts: list[str] = Field(max_length=8)
    approaches: list[Approach] = Field(max_length=2)
    feedback: str
    common_mistakes: list[str]
    follow_ups: list[FollowUp] = Field(min_length=3, max_length=3)
    assessment: InterviewAssessment | None = None


@dataclass
class ModelReply:
    content: InterviewPlan | StudyNotes
    input_tokens: int | None = None
    output_tokens: int | None = None


class ModelRequestError(ValueError):
    """Fixed, safe failure messages; never retain raw provider errors or content."""

    MESSAGES = {
        "authentication": "OpenAI authentication failed. Check OPENAI_API_KEY in api_key.txt or your environment, and project access settings.",
        "quota": "OpenAI reports exhausted API quota or credits. Check API billing, project budget, and usage limits.",
        "rate_limit": "OpenAI rate-limited the request. Wait before starting a new session.",
        "connection": "Could not connect to OpenAI. Check your internet connection, proxy, or firewall.",
        "timeout": "The OpenAI request timed out. No automatic retry was made.",
        "permission": "OpenAI denied access to this request. Check project permissions and model access.",
        "model_unavailable": "The configured model is unavailable to this OpenAI project. Check model access; no model upgrade was made.",
        "invalid_schema": "OpenAI rejected the structured-output schema. Check the adapter's response format.",
        "invalid_request": "OpenAI rejected the request. Check model settings and the response format.",
        "provider_unavailable": "OpenAI is temporarily unavailable. Wait before starting a new session.",
        "output_limit": "The response reached its output limit before completing. No complete, valid response is available; try a narrower topic or shorter source.",
        "refusal": "OpenAI declined this request. No interview review was generated.",
        "invalid_response": "The returned JSON did not satisfy the interview/report rules. No complete, valid response is available.",
        "incomplete": "OpenAI did not return a completed response. No complete, valid response is available.",
        "unknown": "An unexpected client error occurred. Export available content without another call.",
    }

    def __init__(self, kind: str, *, input_tokens: int | None = None,
                 output_tokens: int | None = None):
        self.kind = kind if kind in self.MESSAGES else "unknown"
        self.input_tokens = input_tokens if type(input_tokens) is int and input_tokens >= 0 else None
        self.output_tokens = output_tokens if type(output_tokens) is int and output_tokens >= 0 else None
        super().__init__(f"Model request failed: {self.MESSAGES[self.kind]}")
