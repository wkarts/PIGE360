<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { Pige360SessionClient } from "@pige360/auth";

type Row=Record<string,any>;
const props=defineProps<{api:Pige360SessionClient}>();const emit=defineEmits<{error:[message:string]}>();
const loading=ref(false);const data=ref<Row>({academic:{attendance:{by_status:[]}},finance:{},operations:{service_requests:{by_state:[]}}});
const today=new Date();const end=ref(today.toISOString().slice(0,10));const startDate=new Date(today.getTime()-29*86400000);const start=ref(startDate.toISOString().slice(0,10));
const attendance=computed(()=>data.value.academic?.attendance||{});const finance=computed(()=>data.value.finance||{});const operations=computed(()=>data.value.operations||{});
function money(v:any){return new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(Number(v||0));}
function percent(v:any){return `${Number(v||0).toLocaleString("pt-BR",{maximumFractionDigits:2})}%`;}
function message(e:unknown){return e instanceof Error?e.message:"Falha ao carregar indicadores";}
function barWidth(value:any,items:Row[]){const max=Math.max(1,...items.map(x=>Number(x.value??x.count??0)));return `${Math.max(2,Number(value||0)/max*100)}%`;}
async function load(){loading.value=true;try{data.value=await props.api.request<Row>(`/analytics/overview?from=${encodeURIComponent(start.value)}&to=${encodeURIComponent(end.value)}`);}catch(e){emit("error",message(e));}finally{loading.value=false;}}
onMounted(load);
</script>
<template>
  <section class="panel analytics-filter"><div><h2>Indicadores consolidados</h2><p>Dados calculados diretamente das operações do tenant.</p></div><label>De<input v-model="start" type="date" /></label><label>Até<input v-model="end" type="date" /></label><button class="primary" :disabled="loading" @click="load">{{loading?'Calculando…':'Atualizar'}}</button></section>
  <section class="metrics">
    <article><span>Alunos ativos</span><strong>{{data.academic?.active_students??0}}</strong><small>{{data.academic?.active_enrollments??0}} matrículas ativas</small></article>
    <article><span>Frequência ponderada</span><strong>{{percent(attendance.presence_percentage)}}</strong><small>{{attendance.counted_records??0}} registros segundo políticas vigentes</small></article>
    <article><span>Contas a receber</span><strong>{{money(finance.open_receivables?.balance)}}</strong><small>{{finance.open_receivables?.count??0}} parcelas abertas</small></article>
    <article><span>Vencido</span><strong>{{money(finance.overdue_receivables?.balance)}}</strong><small>{{finance.overdue_receivables?.count??0}} parcelas vencidas</small></article>
    <article><span>Vendas no período</span><strong>{{money(finance.sales?.total)}}</strong><small>{{finance.sales?.count??0}} vendas concluídas</small></article>
    <article><span>Solicitações abertas</span><strong>{{operations.service_requests?.open??0}}</strong><small>{{operations.service_requests?.sla_overdue??0}} fora do SLA</small></article>
  </section>
  <section class="analytics-grid">
    <article class="panel"><div class="panel-title"><h2>Frequência por situação</h2><span>política versionada</span></div><div v-for="x in attendance.by_status||[]" :key="x.status" class="bar-row"><span>{{x.status}}</span><div><i :style="{width:barWidth(x.count,attendance.by_status||[])}"></i></div><strong>{{x.count}}</strong></div><p v-if="!(attendance.by_status||[]).length" class="empty">Sem chamadas no período.</p></article>
    <article class="panel"><div class="panel-title"><h2>Matrículas por turma</h2></div><div v-for="x in data.academic?.enrollments_by_class||[]" :key="x.label" class="bar-row"><span>{{x.label||'Sem turma'}}</span><div><i :style="{width:barWidth(x.value,data.academic?.enrollments_by_class||[])}"></i></div><strong>{{x.value}}</strong></div><p v-if="!(data.academic?.enrollments_by_class||[]).length" class="empty">Sem matrículas ativas.</p></article>
    <article class="panel"><div class="panel-title"><h2>Recebíveis por mês</h2></div><table><thead><tr><th>Mês</th><th>Parcelas</th><th>Saldo</th></tr></thead><tbody><tr v-for="x in finance.receivables_by_month||[]" :key="x.label"><td>{{x.label}}</td><td>{{x.count}}</td><td>{{money(x.value)}}</td></tr><tr v-if="!(finance.receivables_by_month||[]).length"><td colspan="3" class="empty">Sem recebíveis no período.</td></tr></tbody></table></article>
    <article class="panel"><div class="panel-title"><h2>Operação</h2></div><dl class="facts"><div><dt>Posições de estoque</dt><dd>{{operations.inventory?.positions??0}}</dd></div><div><dt>Quantidade em estoque</dt><dd>{{operations.inventory?.quantity??0}}</dd></div><div><dt>Eventos pendentes</dt><dd>{{operations.outbox_pending??0}}</dd></div><div><dt>Última folha</dt><dd>{{operations.latest_payroll?.competence||'—'}} · {{operations.latest_payroll?.state||'—'}}</dd></div><div><dt>Líquido da folha</dt><dd>{{money(operations.latest_payroll?.net_total)}}</dd></div></dl></article>
  </section>
</template>
<style scoped>
.analytics-filter{display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin-bottom:16px}.analytics-filter>div{flex:1;min-width:240px}.analytics-filter label{min-width:150px}.analytics-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.bar-row{display:grid;grid-template-columns:minmax(90px,1fr) minmax(100px,2fr) 54px;gap:10px;align-items:center;margin:10px 0}.bar-row>div{height:10px;background:rgba(128,128,128,.15);border-radius:99px;overflow:hidden}.bar-row i{display:block;height:100%;background:var(--brand-primary);border-radius:99px}.bar-row strong{text-align:right}.facts{display:grid;grid-template-columns:1fr 1fr;gap:10px}.facts div{padding:10px;border:1px solid var(--line,#d9e0e7);border-radius:10px}.facts dt{font-size:.8rem;opacity:.7}.facts dd{margin:4px 0 0;font-weight:700}@media(max-width:900px){.analytics-grid{grid-template-columns:1fr}}
</style>
