export type Role = "platform_super_admin"|"platform_admin"|"tenant_owner"|"institution_director"|"unit_manager"|"secretary"|"academic_coordinator"|"teacher"|"assistant_teacher"|"finance_manager"|"finance_operator"|"fiscal_manager"|"hr_manager"|"personnel_operator"|"payroll_operator"|"timekeeping_operator"|"canteen_manager"|"pos_operator"|"inventory_manager"|"event_manager"|"request_agent"|"mail_admin"|"employee"|"student"|"guardian"|"auditor"|"support";
export type Permission = `${string}.${"read"|"create"|"update"|"delete"|"approve"|"execute"|"manage"}`;
export const hasRole=(roles:readonly string[],...required:Role[])=>required.some(role=>roles.includes(role));
export const requireRole=(roles:readonly string[],...required:Role[])=>{if(!hasRole(roles,...required))throw new Error("Acesso não autorizado para este perfil");};
export const TENANT_ADMIN_ROLES:readonly Role[]=["tenant_owner","institution_director","unit_manager"];
export const PLATFORM_ROLES:readonly Role[]=["platform_super_admin","platform_admin"];
