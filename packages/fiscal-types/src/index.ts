export type FiscalDocumentType="nfe"|"nfce"|"nfse";
export type FiscalEnvironment="homologation"|"production";
export type FiscalDocumentState="draft"|"requested"|"processing"|"authorized"|"rejected"|"cancel_requested"|"cancelled"|"failed";
export type TaxRegime="simples_nacional"|"lucro_presumido"|"lucro_real"|"public_entity"|"other";
export type RtcMode="disabled"|"simulation_only"|"optional_emit"|"required_emit";
export type FiscalClassification={ncm?:string|null;nbs?:string|null;cfop?:string|null;cest?:string|null;cst?:string|null;csosn?:string|null;cstIbsCbs?:string|null;cClassTrib?:string|null;lc116?:string|null;municipalCode?:string|null};
export type FiscalMoney={currency:"BRL";amount:string};
export type FiscalSimulation={documentType:FiscalDocumentType;rulesetVersion:string;taxes:Record<string,FiscalMoney>;approximateIbpt?:FiscalMoney;warnings:string[]};
