export function fixedClock(iso="2026-01-01T12:00:00.000Z"){const at=new Date(iso);return{now:()=>new Date(at),iso:()=>at.toISOString()};}
export function deferred<T>(){let resolve!:(value:T|PromiseLike<T>)=>void;let reject!:(reason?:unknown)=>void;const promise=new Promise<T>((res,rej)=>{resolve=res;reject=rej;});return{promise,resolve,reject};}
export function expectDefined<T>(value:T|null|undefined,label="valor"):T{if(value===null||value===undefined)throw new Error(`${label} deveria estar definido`);return value;}
export function uniqueTestId(prefix="test"){return `${prefix}-${crypto.randomUUID()}`;}
