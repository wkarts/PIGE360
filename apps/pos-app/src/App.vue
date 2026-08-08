<script setup lang="ts">
import { computed,onMounted,reactive,ref } from "vue";
import { Pige360SessionClient,type ApiProblem } from "@pige360/auth";

type Row=Record<string,any>;
type Mode="pos"|"canteen";
const api=new Pige360SessionClient();
const ready=ref(false),auth=ref(false),busy=ref(false),error=ref(""),notice=ref("");
const email=ref(""),password=ref("");
const brand=ref<Row>({});
const products=ref<Row[]>([]),sales=ref<Row[]>([]),cash=ref<Row|null>(null);
const locations=ref<Row[]>([]),students=ref<Row[]>([]),quote=ref<Row|null>(null);
const mode=ref<Mode>("pos"),selectedLocation=ref(""),selectedStudent=ref(""),studentQuery=ref("");
const query=ref(""),payment=ref("pix");
const cart=reactive<Record<string,number>>({});

const school=computed(()=>brand.value.short_name||brand.value.trade_name||brand.value.legal_name||"Instituição");
const visibleProducts=computed(()=>products.value.filter(p=>!query.value||`${p.name} ${p.sku} ${p.barcode||""}`.toLowerCase().includes(query.value.toLowerCase())));
const cartLines=computed(()=>products.value.filter(p=>(cart[p.id]||0)>0).map(p=>({...p,quantity:cart[p.id],line:Number(p.sale_price)*(cart[p.id]||0)})));
const grossTotal=computed(()=>cartLines.value.reduce((a,b)=>a+b.line,0));
const dueTotal=computed(()=>mode.value==="canteen"&&quote.value?Number(quote.value.customer_due||0):grossTotal.value);
const selectedStudentRow=computed(()=>students.value.find(x=>x.id===selectedStudent.value));

function msg(e:unknown){const p=(e as Error&{problem?:ApiProblem})?.problem;return p?.detail||(e instanceof Error?e.message:"Erro inesperado");}
function apply(){document.documentElement.style.setProperty("--brand-primary",brand.value.primary_color||"#006D77");document.documentElement.style.setProperty("--brand-secondary",brand.value.secondary_color||"#0D1B2A");document.title=`${school.value} — PDV`;}
function invalidateQuote(){quote.value=null;}
async function loadStudents(){if(mode.value!=="canteen")return;const q=studentQuery.value.trim();students.value=(await api.request<Row>(`/canteen/pos/students${q?`?q=${encodeURIComponent(q)}`:""}`)).items||[];}
async function load(){brand.value=await api.request<Row>("/branding/current");apply();products.value=(await api.request<Row>("/products")).items||[];sales.value=(await api.request<Row>("/sales")).items||[];locations.value=(await api.request<Row>("/canteen/locations")).items||[];const sessions=(await api.request<Row>("/pos/cash-sessions?state=open")).items||[];cash.value=sessions.find((x:Row)=>x.operator_user_id===api.claims()?.sub)||sessions[0]||null;await loadStudents();}
async function boot(){try{await api.initialize();auth.value=!!api.tokens;if(auth.value)await load();}catch(e){error.value=msg(e);}finally{ready.value=true;}}
async function login(){busy.value=true;error.value="";try{await api.login(email.value,password.value);auth.value=true;await load();}catch(e){error.value=msg(e);}finally{busy.value=false;}}
async function logout(){await api.logout();auth.value=false;}
async function openCash(){try{cash.value=await api.request<Row>("/pos/cash-sessions/open",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({terminal_code:"PDV-01",opening_amount:"0.00"})});notice.value="Caixa aberto.";}catch(e){error.value=msg(e);}}
function add(p:Row){cart[p.id]=(cart[p.id]||0)+1;invalidateQuote();}
function remove(p:Row){cart[p.id]=Math.max(0,(cart[p.id]||0)-1);invalidateQuote();}
function changeMode(){invalidateQuote();if(mode.value==="pos"){selectedLocation.value="";selectedStudent.value="";payment.value="pix";}else{payment.value="wallet";void loadStudents();}}
async function calculateQuote(){
  error.value="";
  if(mode.value!=="canteen")return null;
  if(!selectedLocation.value||!selectedStudent.value){error.value="Selecione a cantina e o aluno antes de calcular a venda.";return null;}
  if(!cartLines.value.length){error.value="Adicione pelo menos um produto.";return null;}
  try{
    quote.value=await api.request<Row>("/canteen/quote",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({canteen_location_id:selectedLocation.value,student_id:selectedStudent.value,items:cartLines.value.map(x=>({product_id:x.id,quantity:String(x.quantity)}))})});
    return quote.value;
  }catch(e){quote.value=null;error.value=msg(e);return null;}
}
async function sell(){
  if(!cash.value){error.value="Abra o caixa antes de vender.";return;}
  if(!cartLines.value.length)return;
  busy.value=true;error.value="";
  try{
    const q=mode.value==="canteen"?await calculateQuote():null;
    if(mode.value==="canteen"&&!q)return;
    const due=mode.value==="canteen"?Number(q?.customer_due||0):grossTotal.value;
    const payments=due>0?[{method:payment.value,amount:due.toFixed(2)}]:[];
    await api.request("/sales",{method:"POST",headers:{"Content-Type":"application/json","Idempotency-Key":`pdv-${crypto.randomUUID()}`},body:JSON.stringify({cash_session_id:cash.value.id,channel:mode.value,canteen_location_id:mode.value==="canteen"?selectedLocation.value:null,student_id:mode.value==="canteen"?selectedStudent.value:null,items:cartLines.value.map(x=>({product_id:x.id,quantity:String(x.quantity),discount:"0"})),payments,discount:"0",request_fiscal_document:true})});
    Object.keys(cart).forEach(k=>delete cart[k]);quote.value=null;notice.value=mode.value==="canteen"?"Venda da cantina concluída com políticas, carteira, estoque e fiscal integrados.":"Venda concluída e integrada ao estoque/financeiro/fiscal.";await load();
  }catch(e){error.value=msg(e);}finally{busy.value=false;}
}
async function closeCash(){if(!cash.value)return;try{await api.request(`/pos/cash-sessions/${cash.value.id}/close`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({closing_amount:"0.00",reason:"Fechamento operacional do terminal"})});cash.value=null;notice.value="Caixa fechado.";}catch(e){error.value=msg(e);}}
onMounted(boot);
</script>

<template>
<div v-if="!ready" class="center">Inicializando PDV…</div>
<div v-else-if="!auth" class="login-page"><form class="login-card" @submit.prevent="login"><div class="mark">▧</div><span class="eyebrow">PDV / Cantina</span><h1>Entrar no terminal</h1><label>E-mail<input v-model="email" type="email" required></label><label>Senha<input v-model="password" type="password" required></label><p v-if="error" class="flash error">{{error}}</p><button class="primary" :disabled="busy">Entrar</button></form></div>
<div v-else class="mobile-shell">
<header><div class="brand"><div class="mark">▧</div><div><strong>{{school}}</strong><small>PDV e Cantina</small></div></div><div><span class="cash-state">{{cash?'Caixa aberto':'Caixa fechado'}}</span><button class="ghost" @click="logout">Sair</button></div></header>
<main>
<div v-if="error" class="flash error">{{error}}</div><div v-if="notice" class="flash success">{{notice}}</div>
<section class="toolbar"><select v-model="mode" class="mode-select" @change="changeMode"><option value="pos">PDV geral</option><option value="canteen">Cantina escolar</option></select><input v-model="query" placeholder="Buscar produto, SKU ou código de barras"><button v-if="!cash" class="primary" @click="openCash">Abrir caixa</button><button v-else class="ghost-dark" @click="closeCash">Fechar caixa</button></section>
<section v-if="mode==='canteen'" class="panel canteen-context"><div class="section-title"><h2>Contexto da cantina</h2><span>Políticas validadas no servidor</span></div><div class="context-grid"><label>Cantina<select v-model="selectedLocation" @change="invalidateQuote"><option value="">Selecione…</option><option v-for="l in locations" :key="l.id" :value="l.id">{{l.name}}</option></select></label><label>Buscar aluno<div class="student-search"><input v-model="studentQuery" placeholder="Nome ou matrícula" @keyup.enter="loadStudents"><button class="ghost-dark" @click="loadStudents">Buscar</button></div></label><label>Aluno<select v-model="selectedStudent" @change="invalidateQuote"><option value="">Selecione…</option><option v-for="s in students" :key="s.id" :value="s.id">{{s.social_name||s.full_name}} · {{s.registration_number}}</option></select></label></div><div v-if="selectedStudentRow" class="wallet-chip">Carteira: <strong>{{selectedStudentRow.wallet_balance==null?'não cadastrada':`R$ ${Number(selectedStudentRow.wallet_balance).toFixed(2)}`}}</strong></div></section>
<section class="pos-grid"><div class="panel"><div class="section-title"><h2>Produtos</h2><span>{{visibleProducts.length}} itens</span></div><div class="product-grid"><button v-for="p in visibleProducts" :key="p.id" class="product" @click="add(p)" :disabled="Number(p.stock_quantity)<=0"><strong>{{p.name}}</strong><small>{{p.sku}} · estoque {{p.stock_quantity}}</small><b>R$ {{Number(p.sale_price).toFixed(2)}}</b></button></div></div>
<aside class="panel cart"><div class="section-title"><h2>Venda</h2><span>{{cartLines.length}} itens</span></div><div v-for="line in cartLines" :key="line.id" class="cart-line"><div><strong>{{line.name}}</strong><small>R$ {{Number(line.sale_price).toFixed(2)}} × {{line.quantity}}</small></div><div class="qty"><button @click="remove(line)">−</button><span>{{line.quantity}}</span><button @click="add(line)">+</button></div></div><p v-if="!cartLines.length" class="empty">Adicione produtos para iniciar a venda.</p>
<div v-if="mode==='canteen'" class="quote-box"><button class="ghost-dark" :disabled="!cartLines.length" @click="calculateQuote">Calcular políticas e subsídio</button><template v-if="quote"><div><span>Valor comercial</span><strong>R$ {{Number(quote.total_amount).toFixed(2)}}</strong></div><div><span>Subsídio</span><strong>− R$ {{Number(quote.subsidy_amount).toFixed(2)}}</strong></div><div class="due"><span>Devido pelo aluno</span><strong>R$ {{Number(quote.customer_due).toFixed(2)}}</strong></div><small>Carteira: {{quote.wallet_balance==null?'não cadastrada':`R$ ${Number(quote.wallet_balance).toFixed(2)}`}} · consumo diário R$ {{Number(quote.daily_spent||0).toFixed(2)}}</small></template></div>
<div v-else class="total"><span>Total</span><strong>R$ {{grossTotal.toFixed(2)}}</strong></div>
<label v-if="dueTotal>0">Pagamento<select v-model="payment"><option v-if="mode==='canteen'" value="wallet">Carteira</option><option value="pix">PIX</option><option value="cash">Dinheiro</option><option value="card">Cartão</option></select></label><p v-else-if="mode==='canteen'&&quote" class="free-meal">Refeição integralmente subsidiada — nenhum pagamento do aluno.</p><button class="primary" :disabled="busy||!cash||!cartLines.length" @click="sell">Concluir venda</button></aside></section>
<section class="panel"><div class="section-title"><h2>Últimas vendas</h2></div><div class="list-row" v-for="s in sales.slice(0,10)" :key="s.id"><div><strong>#{{s.id.slice(-8)}}</strong><span>{{s.channel}} · {{s.state}}</span></div><strong>R$ {{Number(s.total_amount).toFixed(2)}}</strong></div></section>
</main></div>
</template>
