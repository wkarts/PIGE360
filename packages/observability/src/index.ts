export type RequestTrace={requestId:string;correlationId:string;startedAt:number};
export function requestTrace(correlationId=crypto.randomUUID()):RequestTrace{return{requestId:crypto.randomUUID(),correlationId,startedAt:performance.now()};}
export function traceHeaders(trace:RequestTrace):HeadersInit{return{"X-Request-ID":trace.requestId,"X-Correlation-ID":trace.correlationId};}
export function elapsedMs(trace:RequestTrace):number{return Math.max(0,Math.round((performance.now()-trace.startedAt)*100)/100);}
export function safeError(error:unknown){const e=error as {name?:string;message?:string;status?:number;problem?:{code?:string;correlation_id?:string}};return{name:e?.name??"Error",message:e?.message??"Erro desconhecido",status:e?.status,code:e?.problem?.code,correlationId:e?.problem?.correlation_id};}
