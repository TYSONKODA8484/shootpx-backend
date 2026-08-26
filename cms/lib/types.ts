export interface FieldConfig {
  name: string;
  kind: "string" | "int" | "float" | "bool" | "datetime" | "json" | "enum" | "fk";
  editable: boolean;
  enum_values: string[] | null;
  fk_entity: string | null;
  help_text: string | null;
}

export interface EntityConfig {
  name: string;
  label: string;
  pk_field: string;
  pk_provided_on_create: boolean;
  allow_create: boolean;
  allow_update: boolean;
  allow_delete: boolean;
  search_fields: string[];
  fields: FieldConfig[];
}

export interface PaginatedResponse {
  items: Record<string, unknown>[];
  total: number;
  page: number;
  page_size: number;
}

export interface Stats {
  total_users: number;
  total_teams: number;
  subscriptions_by_plan: Record<string, number>;
  total_credit_balance: number;
}
