export const digits=(value:string)=>value.replace(/\D/g,"");
function repeated(value:string){return /^([0-9])\1+$/.test(value);}
export function validCpf(value:string):boolean{const n=digits(value);if(n.length!==11||repeated(n))return false;for(let p=9;p<=10;p++){let sum=0;for(let i=0;i<p;i++)sum+=Number(n[i])*(p+1-i);let d=(sum*10)%11;if(d===10)d=0;if(d!==Number(n[p]))return false;}return true;}
export function validCnpj(value:string):boolean{const n=digits(value);if(n.length!==14||repeated(n))return false;const calc=(base:string,weights:number[])=>{const sum=base.split("").reduce((a,d,i)=>a+Number(d)*weights[i]!,0);const r=sum%11;return r<2?0:11-r;};const d1=calc(n.slice(0,12),[5,4,3,2,9,8,7,6,5,4,3,2]);const d2=calc(n.slice(0,12)+d1,[6,5,4,3,2,9,8,7,6,5,4,3,2]);return n.endsWith(`${d1}${d2}`);}
export function validEmail(value:string):boolean{return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());}
export function required<T>(value:T|null|undefined,message="Campo obrigatório"):T{if(value===null||value===undefined||value==="" as T)throw new Error(message);return value;}
