from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

TERMINALS = {"completed", "rejected", "cancelled"}


class WorkflowStep(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    name: str = Field(min_length=2, max_length=160)
    type: Literal["approval", "task"] = "approval"
    approval_mode: Literal["any", "all"] = "any"
    assignee_roles: list[str] = Field(default_factory=list, max_length=20)
    assignee_user_id: str | None = None
    due_hours: int | None = Field(default=None, ge=1, le=8760)
    approve_to: str = "completed"
    reject_to: str = "rejected"

    @model_validator(mode="after")
    def validate_assignee(self) -> "WorkflowStep":
        if not self.assignee_roles and not self.assignee_user_id:
            raise ValueError("Cada etapa deve possuir assignee_roles ou assignee_user_id.")
        if self.type == "task" and self.approval_mode != "any":
            raise ValueError("Tarefas operacionais usam approval_mode=any.")
        if self.approval_mode == "all" and len(self.assignee_roles) + (1 if self.assignee_user_id else 0) < 2:
            raise ValueError("approval_mode=all exige ao menos dois destinatários independentes.")
        return self


class WorkflowGraph(BaseModel):
    steps: list[WorkflowStep] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_graph(self) -> "WorkflowGraph":
        keys = [step.key for step in self.steps]
        if len(keys) != len(set(keys)):
            raise ValueError("As chaves das etapas devem ser únicas.")
        allowed = set(keys) | TERMINALS
        for step in self.steps:
            if step.approve_to not in allowed:
                raise ValueError(f"Destino approve_to inválido em {step.key}: {step.approve_to}")
            if step.reject_to not in allowed:
                raise ValueError(f"Destino reject_to inválido em {step.key}: {step.reject_to}")
            if step.approve_to == step.key or step.reject_to == step.key:
                raise ValueError(f"A etapa {step.key} não pode apontar para si própria.")
        # Detecta ciclos alcançáveis seguindo o caminho de aprovação. Ciclos humanos
        # arbitrários exigiriam uma política explícita de repetição, que não é aceita
        # silenciosamente neste motor.
        mapping = {step.key: step.approve_to for step in self.steps}
        current = self.steps[0].key
        seen: set[str] = set()
        while current not in TERMINALS:
            if current in seen:
                raise ValueError("O fluxo de aprovação contém ciclo não permitido.")
            seen.add(current)
            current = mapping[current]
        return self

    def step(self, key: str) -> WorkflowStep:
        for item in self.steps:
            if item.key == key:
                return item
        raise KeyError(key)
