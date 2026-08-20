from typing import Literal

from pydantic import BaseModel, Field, model_validator


class GenerateRequest(BaseModel):
    type: Literal["api_call", "ai_tokens"]
    input_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def cached_within_input(self):
        if self.type == "ai_tokens" and self.cached_tokens > self.input_tokens:
            raise ValueError("cached_tokens cannot exceed input_tokens")
        return self


class CheckoutRequest(BaseModel):
    plan: Literal["pro"] = "pro"
