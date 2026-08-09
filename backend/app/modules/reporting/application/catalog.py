from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ReportDefinition:
    code: str
    title: str
    description: str
    formats: tuple[str, ...]
    roles: frozenset[str]
    columns: tuple[tuple[str, str], ...]
    required_parameters: tuple[str, ...] = ()

ADMIN = frozenset({"tenant_owner","institution_director","unit_manager"})
CATALOG: dict[str, ReportDefinition] = {
    "enrollments": ReportDefinition("enrollments","Matrículas","Alunos, turma, programa, período e situação.",( "pdf","xlsx","csv"),ADMIN|{"secretary","academic_coordinator","auditor"},(("registration_number","Matrícula"),("student_name","Aluno"),("class_name","Turma"),("program_name","Programa"),("state","Situação"),("starts_on","Início"),("ends_on","Fim"))),
    "finance_receivables": ReportDefinition("finance_receivables","Contas a receber","Parcelas, vencimentos, valores e saldo.",( "pdf","xlsx","csv"),ADMIN|{"finance_manager","finance_operator","auditor"},(("student_name","Aluno"),("contract_number","Contrato"),("installment_number","Parcela"),("due_date","Vencimento"),("amount","Valor"),("paid_amount","Pago"),("balance","Saldo"),("state","Situação"))),
    "attendance_summary": ReportDefinition("attendance_summary","Resumo de frequência","Frequência consolidada por aluno.",( "pdf","xlsx","csv"),ADMIN|{"academic_coordinator","secretary","auditor"},(("student_name","Aluno"),("registration_number","Matrícula"),("total_records","Registros"),("present_count","Presenças"),("absence_count","Faltas"),("late_count","Atrasos"))),
    "inventory_stock": ReportDefinition("inventory_stock","Posição de estoque","Saldo físico por produto e depósito.",( "pdf","xlsx","csv"),ADMIN|{"inventory_manager","canteen_manager","auditor"},(("sku","SKU"),("product_name","Produto"),("warehouse","Depósito"),("quantity","Quantidade"),("updated_at","Atualizado em"))),
    "payroll_run": ReportDefinition("payroll_run","Folha de pagamento","Resumo da folha por colaborador.",( "pdf","xlsx","csv"),ADMIN|{"hr_manager","payroll_operator","personnel_operator","auditor"},(("employee_name","Colaborador"),("employee_number","Matrícula funcional"),("gross_amount","Proventos"),("discount_amount","Descontos"),("net_amount","Líquido"),("state","Situação")),("run_id",)),
    "teaching_plan_coverage": ReportDefinition("teaching_plan_coverage","Cobertura do planejamento","Planos por turma/componente e execução.",( "pdf","xlsx","csv"),ADMIN|{"academic_coordinator","auditor"},(("class_name","Turma"),("component_name","Componente"),("title","Plano"),("status","Situação"),("version","Versão"),("period_label","Período"))),
}


def definition(code: str) -> ReportDefinition | None:
    return CATALOG.get(code)


def public_catalog(roles: set[str]) -> list[dict[str, Any]]:
    return [
        {"code": item.code,"title": item.title,"description": item.description,"formats": list(item.formats),"required_parameters": list(item.required_parameters)}
        for item in CATALOG.values() if item.roles.intersection(roles)
    ]
