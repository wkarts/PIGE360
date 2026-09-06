export type EntityFieldType =
  | "text"
  | "number"
  | "date"
  | "time"
  | "textarea"
  | "checkbox"
  | "select"
  | "password"
  | "email"
  | "tel";

export interface EntityField {
  key: string;
  label: string;
  type?: EntityFieldType;
  required?: boolean;
  relationEntity?: string;
  placeholder?: string;
}

export interface EntityConfig {
  key: string;
  title: string;
  route: string;
  columns: string[];
  fields: EntityField[];
}

export const entityConfigs: Record<string, EntityConfig> = {
  departamentos: {
    key: "departamentos",
    title: "Departamentos",
    route: "/departamentos",
    columns: ["id", "descricao", "ativo"],
    fields: [
      { key: "descricao", label: "Descrição", required: true },
      { key: "ativo", label: "Ativo", type: "checkbox" }
    ]
  },
  funcoes: {
    key: "funcoes",
    title: "Funções/Cargos",
    route: "/funcoes",
    columns: ["id", "descricao", "ativo"],
    fields: [
      { key: "descricao", label: "Descrição", required: true },
      { key: "ativo", label: "Ativo", type: "checkbox" }
    ]
  },
  centro_custos: {
    key: "centro_custos",
    title: "Centros de custo",
    route: "/centros-custo",
    columns: ["id", "codigo", "descricao", "ativo"],
    fields: [
      { key: "codigo", label: "Código" },
      { key: "descricao", label: "Descrição", required: true },
      { key: "ativo", label: "Ativo", type: "checkbox" }
    ]
  },
  clientes: {
    key: "clientes",
    title: "Clientes",
    route: "/clientes",
    columns: ["id", "nome", "documento", "telefone", "email", "ativo"],
    fields: [
      { key: "nome", label: "Nome/Razão social", required: true },
      { key: "documento", label: "CPF/CNPJ" },
      { key: "telefone", label: "Telefone", type: "tel" },
      { key: "email", label: "E-mail", type: "email" },
      { key: "endereco", label: "Endereço" },
      { key: "cidade", label: "Cidade" },
      { key: "estado", label: "UF" },
      { key: "observacoes", label: "Observações", type: "textarea" },
      { key: "ativo", label: "Ativo", type: "checkbox" }
    ]
  },
  fornecedores: {
    key: "fornecedores",
    title: "Fornecedores",
    route: "/fornecedores",
    columns: ["id", "nome", "documento", "telefone", "email", "ativo"],
    fields: [
      { key: "nome", label: "Nome/Razão social", required: true },
      { key: "documento", label: "CPF/CNPJ" },
      { key: "telefone", label: "Telefone", type: "tel" },
      { key: "email", label: "E-mail", type: "email" },
      { key: "endereco", label: "Endereço" },
      { key: "cidade", label: "Cidade" },
      { key: "estado", label: "UF" },
      { key: "observacoes", label: "Observações", type: "textarea" },
      { key: "ativo", label: "Ativo", type: "checkbox" }
    ]
  },
  produtos: {
    key: "produtos",
    title: "Produtos/Serviços",
    route: "/produtos",
    columns: ["id", "codigo", "descricao", "tipo", "ativo"],
    fields: [
      { key: "codigo", label: "Código" },
      { key: "descricao", label: "Descrição", required: true },
      { key: "tipo", label: "Tipo", placeholder: "produto ou serviço" },
      { key: "unidade", label: "Unidade" },
      { key: "valor", label: "Valor", type: "number" },
      { key: "ativo", label: "Ativo", type: "checkbox" }
    ]
  }
};
