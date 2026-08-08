import type { Pige360SessionClient } from "@pige360/auth";

export type MailAddress = { name?: string; email: string };
export type MailFolder = { id:string; remote_name:string; display_name:string; special_use?:string|null; unread_count:number; total_count:number; highest_uid:number };
export type MailMessage = {
  id:string; remote_uid:number; message_id?:string|null; thread_key:string; subject?:string|null;
  sender?:MailAddress; recipients?:MailAddress[]; cc?:MailAddress[]; bcc?:MailAddress[];
  received_at?:string|null; sent_at?:string|null; flags?:string[]; preview?:string|null;
  has_attachments:boolean|number; folder_name:string;
};
export type MailAttachment = { filename:string; content_type:string; size_bytes:number; sha256:string };
export type MailStatus = { account:Record<string,unknown>; folders:MailFolder[] };
export type MailDraft = { id:string; subject?:string|null; version:number; state:string; to?:string[]; cc?:string[]; bcc?:string[]; body_text?:string };
export type SendMailInput = { to:string[]; cc?:string[]; bcc?:string[]; subject?:string; body_text:string; body_html?:string|null };

export class Pige360MailClient {
  constructor(private readonly api:Pige360SessionClient) {}
  status(){ return this.api.request<MailStatus>("/mail/me/status"); }
  sync(){ return this.api.request<{run_id:string;state:string;folders_synced:number;messages_synced:number;finished_at:string}>("/mail/me/sync",{method:"POST"}); }
  list(folder?:string,search?:string){ const q=new URLSearchParams(); if(folder)q.set("folder",folder); if(search)q.set("search",search); return this.api.request<{items:MailMessage[]}>(`/mail/me/messages?${q}`); }
  message(id:string){ return this.api.request<{metadata:MailMessage;content:{text:string;html?:string|null;attachments:MailAttachment[]}}>(`/mail/me/messages/${encodeURIComponent(id)}`); }
  send(data:SendMailInput,key=crypto.randomUUID()){ return this.api.request("/mail/me/send",{method:"POST",headers:{"Content-Type":"application/json","Idempotency-Key":`mail-${key}`},body:JSON.stringify(data)}); }
  seen(id:string,value:boolean){ return this.api.request(`/mail/me/messages/${encodeURIComponent(id)}/seen`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({seen:value})}); }
  move(id:string,destinationFolder:string){ return this.api.request(`/mail/me/messages/${encodeURIComponent(id)}/move`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({destination_folder:destinationFolder})}); }
  trash(id:string){ return this.api.request(`/mail/me/messages/${encodeURIComponent(id)}/trash`,{method:"POST"}); }
  reply(id:string,bodyText:string,replyAll=false,key=crypto.randomUUID()){ return this.api.request(`/mail/me/messages/${encodeURIComponent(id)}/reply`,{method:"POST",headers:{"Content-Type":"application/json","Idempotency-Key":`mail-reply-${key}`},body:JSON.stringify({body_text:bodyText,reply_all:replyAll})}); }
  forward(id:string,data:SendMailInput,key=crypto.randomUUID()){ return this.api.request(`/mail/me/messages/${encodeURIComponent(id)}/forward`,{method:"POST",headers:{"Content-Type":"application/json","Idempotency-Key":`mail-forward-${key}`},body:JSON.stringify(data)}); }
  async attachment(id:string,index:number):Promise<{blob:Blob;sha256:string|null;filename:string|null}>{
    const response=await this.api.response(`/mail/me/messages/${encodeURIComponent(id)}/attachments/${index}`,{headers:{Accept:"application/octet-stream"}});
    const disposition=response.headers.get("content-disposition")??"";
    const filename=/filename="([^"]+)"/.exec(disposition)?.[1]??null;
    return {blob:await response.blob(),sha256:response.headers.get("x-content-sha256"),filename};
  }
}
