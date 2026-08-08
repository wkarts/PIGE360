<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import type { Pige360SessionClient } from "@pige360/auth";

type Row = Record<string, any>;
type CatalogItem = { code:string; title:string; description:string; formats:string[]; required_parameters:string[] };
const props=defineProps<{api:Pige360SessionClient}>();
const emit=defineEmits<{error:[message:string]}>
();
const loading=ref(false);const catalog=ref<CatalogItem[]>([]);const runs=ref<Row[]>([]);const payrollRuns=ref<Row[]>([]);
const selected=ref("");const format=ref("pdf");const parameters=reactive<Record<string,string>>({});
const current=computed(()=>catalog.value.find(x=>x.code===selected.value));
const required=computed(()=>current.value?.required_parameters||[]);
function message(e:unknown){return e instanceof Error?e.message:"Falha ao processar relatório";}
function dateBR(v:any){if(!v)return "—";try{return new Intl.DateTimeFormat("pt-BR",{dateStyle:"short",timeStyle:"short"}).format(new Date(String(v)));}catch{return String(v)}}
function select(code:string){selected.value=code;const item=catalog.value.find(x=>x.code===code);format.value=item?.formats[0]||"pdf";for(const key of Object.keys(parameters))delete parameters[key];}
async function load(){loading.value=true;try{const [c,r,p]=await Promise.all([props.api.request<Row>("/reports/catalog"),props.api.request<Row>("/reports/runs"),props.api.request<Row>("/payroll/runs").catch(()=>({items:[]}))]);catalog.value=c.items||[];runs.value=r.items||[];payrollRuns.value=p.items||[];if(!selected.value&&catalog.value[0])select(catalog.value[0].code);}catch(e){emit("error",message(e));}finally{loading.value=false;}}
async function run(){if(!current.value)return;loading.value=true;try{const clean:Record<string,string>={};for(const key of required.value){if(parameters[key])clean[key]=parameters[key];}await props.api.request("/reports/runs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({report_code:selected.value,format:format.value,parameters:clean})});await load();}catch(e){emit("error",message(e));}finally{loading.value=false;}}
async function sha256(data:ArrayBuffer){const digest=await crypto.subtle.digest("SHA-256",data);return [...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,"0")).join("");}
async function download(row:Row){loading.value=true;try{const response=await props.api.response(`/reports/runs/${row.id}/download`);const data=await response.arrayBuffer();const expected=(response.headers.get("x-content-sha256")||"").toLowerCase();const actual=await sha256(data);if(expected&&actual!==expected)throw new Error("Integridade do relatório inválida: SHA-256 divergente.");const blob=new Blob([data],{type:response.headers.get("content-type")||"application/octet-stream"});const disposition=response.headers.get("content-disposition")||"";const name=/filename="?([^";]+)"?/i.exec(disposition)?.[1]||`${row.report_code}.${row.format}`;const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download=name;a.click();URL.revokeObjectURL(url);}catch(e){emit("error",message(e));}finally{loading.value=false;}}
onMounted(load);
</script>
<template>
  <section class="report-layout">
    <aside class="panel report-catalog"><div class="panel-title"><h2>Catálogo de relatórios</h2><span>{{catalog.length}}</span></div><button v-for="item in catalog" :key="item.code" class="report-choice" :class="{selected:selected===item.code}" @click="select(item.code)"><strong>{{item.title}}</strong><small>{{item.description}}</small></button><p v-if="!catalog.length" class="empty">Nenhum relatório liberado para seu perfil.</p></aside>
    <form class="panel report-run" @submit.prevent="run"><div class="panel-title"><div><h2>{{current?.title||'Relatório'}}</h2><p>{{current?.description}}</p></div></div><label>Formato<select v-model="format"><option v-for="f in current?.formats||[]" :key="f" :value="f">{{f.toUpperCase()}}</option></select></label><template v-for="field in required" :key="field"><label v-if="field==='run_id'">Folha de pagamento<select v-model="parameters[field]" required><option value="">Selecione</option><option v-for="r in payrollRuns" :key="r.id" :value="r.id">{{r.competence}} · {{r.run_type}} · {{r.state}}</option></select></label><label v-else>{{field}}<input v-model="parameters[field]" required /></label></template><button class="primary" :disabled="loading||!current">{{loading?'Processando…':'Gerar relatório'}}</button><small>O arquivo é armazenado no bucket do tenant e validado por SHA-256 no download.</small></form>
  </section>
  <section class="panel"><div class="panel-title"><h2>Execuções</h2><button class="small" @click="load">Atualizar</button></div><table><thead><tr><th>Relatório</th><th>Formato</th><th>Registros</th><th>Estado</th><th>Solicitado</th><th></th></tr></thead><tbody><tr v-for="r in runs" :key="r.id"><td>{{catalog.find(x=>x.code===r.report_code)?.title||r.report_code}}</td><td>{{String(r.format).toUpperCase()}}</td><td>{{r.rows_count??'—'}}</td><td><span class="pill" :class="r.state==='completed'?'ok':r.state==='failed'?'danger':'warn'">{{r.state}}</span></td><td>{{dateBR(r.requested_at)}}</td><td><button v-if="r.state==='completed'" class="small" @click="download(r)">Baixar</button></td></tr><tr v-if="!runs.length"><td colspan="6" class="empty">Nenhum relatório gerado.</td></tr></tbody></table></section>
</template>
<style scoped>
.report-layout{display:grid;grid-template-columns:minmax(260px,.75fr) minmax(320px,1.25fr);gap:16px;margin-bottom:16px}.report-catalog{display:flex;flex-direction:column;gap:8px}.report-choice{display:flex;flex-direction:column;align-items:flex-start;text-align:left;padding:12px;border:1px solid var(--line,#d9e0e7);border-radius:10px;background:transparent;cursor:pointer}.report-choice small{opacity:.72;margin-top:4px}.report-choice.selected{border-color:var(--brand-primary);box-shadow:0 0 0 1px var(--brand-primary)}.report-run{display:flex;flex-direction:column;gap:12px}@media(max-width:900px){.report-layout{grid-template-columns:1fr}}
</style>
