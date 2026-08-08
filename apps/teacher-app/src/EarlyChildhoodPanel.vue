<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import type { Pige360SessionClient } from "@pige360/auth";

type Row=Record<string,any>;
const props=defineProps<{api:Pige360SessionClient;assignments:Row[]}>();
const emit=defineEmits<{notice:[string];error:[string]}>();
const infantLevels=new Set(["infantil","educacao_infantil","educação_infantil","early_childhood"]);
const infantAssignments=computed(()=>props.assignments.filter(a=>infantLevels.has(String(a.education_level||"").toLowerCase().replace(/ /g,"_"))));
const assignmentId=ref("");const students=ref<Row[]>([]);const selectedStudent=ref("");const history=ref<Row[]>([]);const guardians=ref<Row[]>([]);const busy=ref(false);
const form=reactive({record_date:new Date().toISOString().slice(0,10),mood:"",meal:"",consumption:"completo",sleep_start:"",sleep_end:"",hygiene:"",diaper_change:"",development_notes:""});
const pickup=reactive({guardian_id:"",released_at:"",identity_document_masked:"",notes:""});
function message(e:unknown){return e instanceof Error?e.message:"Erro ao operar agenda infantil";}
async function loadStudents(){students.value=[];selectedStudent.value="";history.value=[];guardians.value=[];if(!assignmentId.value)return;busy.value=true;try{const r=await props.api.request<Row>(`/portal/teacher/assignments/${assignmentId.value}/students`);students.value=r.items||[];}catch(e){emit("error",message(e));}finally{busy.value=false;}}
async function loadStudent(){history.value=[];guardians.value=[];if(!selectedStudent.value)return;busy.value=true;try{const [d,g]=await Promise.all([props.api.request<Row>(`/academic/early-childhood/students/${selectedStudent.value}/daily-records`),props.api.request<Row>(`/academic/early-childhood/students/${selectedStudent.value}/authorized-pickups`)]);history.value=d.items||[];guardians.value=g.items||[];}catch(e){emit("error",message(e));}finally{busy.value=false;}}
async function save(){if(!selectedStudent.value)return;busy.value=true;try{const body={student_id:selectedStudent.value,record_date:form.record_date,meals:form.meal?[{meal:form.meal,consumption:form.consumption}]:[],sleep:form.sleep_start?{started_at:form.sleep_start,ended_at:form.sleep_end||null}: {},hygiene:form.hygiene?[{type:form.hygiene}]:[],diaper_changes:form.diaper_change?[{type:form.diaper_change}]:[],mood:form.mood||null,development_notes:form.development_notes||null,authorized_photos:[]};await props.api.request("/academic/early-childhood/daily-records",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});emit("notice","Agenda diária registrada.");await loadStudent();}catch(e){emit("error",message(e));}finally{busy.value=false;}}
async function release(){if(!selectedStudent.value||!pickup.guardian_id||!pickup.released_at)return;busy.value=true;try{await props.api.request("/academic/early-childhood/pickups",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({student_id:selectedStudent.value,guardian_id:pickup.guardian_id,released_at:new Date(pickup.released_at).toISOString(),identity_document_masked:pickup.identity_document_masked||null,notes:pickup.notes||null})});emit("notice","Retirada registrada com responsável autorizado.");Object.assign(pickup,{guardian_id:"",released_at:"",identity_document_masked:"",notes:""});await loadStudent();}catch(e){emit("error",message(e));}finally{busy.value=false;}}
watch(assignmentId,()=>void loadStudents());watch(selectedStudent,()=>void loadStudent());
</script>
<template>
<section v-if="infantAssignments.length" class="panel early-childhood">
  <div class="section-title"><div><h2>Agenda da Educação Infantil</h2><small>Rotina diária, desenvolvimento e retirada autorizada.</small></div><span class="pill">{{infantAssignments.length}} turma(s)</span></div>
  <div class="cols">
    <label>Atribuição<select v-model="assignmentId"><option value="">Selecione</option><option v-for="a in infantAssignments" :key="a.id" :value="a.id">{{a.class_group_name}} — {{a.component_name}}</option></select></label>
    <label>Aluno<select v-model="selectedStudent" :disabled="!assignmentId"><option value="">Selecione</option><option v-for="s in students" :key="s.student_id" :value="s.student_id">{{s.social_name||s.full_name}} — {{s.registration_number}}</option></select></label>
  </div>
  <div v-if="selectedStudent" class="grid">
    <form class="form subpanel" @submit.prevent="save">
      <h3>Registro do dia</h3><label>Data<input v-model="form.record_date" type="date" required></label>
      <div class="cols"><label>Humor<input v-model="form.mood" placeholder="alegre, tranquilo…"></label><label>Alimentação<input v-model="form.meal" placeholder="almoço"></label></div>
      <label v-if="form.meal">Consumo<select v-model="form.consumption"><option value="completo">Completo</option><option value="parcial">Parcial</option><option value="recusado">Recusado</option></select></label>
      <div class="cols"><label>Início do sono<input v-model="form.sleep_start" type="time"></label><label>Fim do sono<input v-model="form.sleep_end" type="time"></label></div>
      <div class="cols"><label>Higiene<input v-model="form.hygiene" placeholder="lavagem das mãos"></label><label>Troca<input v-model="form.diaper_change" placeholder="troca de fralda/roupa"></label></div>
      <label>Desenvolvimento e observações<textarea v-model="form.development_notes" rows="4"></textarea></label><button :disabled="busy">Salvar agenda</button>
    </form>
    <form class="form subpanel" @submit.prevent="release">
      <h3>Retirada do aluno</h3><label>Responsável autorizado<select v-model="pickup.guardian_id" required><option value="">Selecione</option><option v-for="g in guardians" :key="g.guardian_id" :value="g.guardian_id">{{g.social_name||g.full_name}} — {{g.relationship}}</option></select></label>
      <label>Data/hora da retirada<input v-model="pickup.released_at" type="datetime-local" required></label><label>Documento conferido (mascarado)<input v-model="pickup.identity_document_masked" placeholder="CPF ***.***.***-00"></label><label>Observação<textarea v-model="pickup.notes" rows="3"></textarea></label><button :disabled="busy||!guardians.length">Registrar retirada</button><small v-if="!guardians.length">Nenhum responsável autorizado para retirada.</small>
    </form>
  </div>
  <div v-if="history.length" class="rows history"><div v-for="r in history.slice(0,10)" :key="r.id"><div><strong>{{r.record_date}} · {{r.mood||'Rotina registrada'}}</strong><small>{{r.development_notes||'Sem observação de desenvolvimento.'}}</small></div><span class="pill">v{{r.version}}</span></div></div>
</section>
</template>
