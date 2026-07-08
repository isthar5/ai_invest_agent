import type { Node, Edge } from "@xyflow/react";

/** Node type identifiers */
export type GraphNodeType =
  | "enterprise"
  | "legal-person"
  | "supplier"
  | "customer"
  | "bank"
  | "tax"
  | "policy"
  | "knowledge";

/** Extra data attached to each custom node */
export interface GraphNodeData extends Record<string, unknown> {
  label: string;
  nodeType: GraphNodeType;
  category: string;
  properties: { key: string; value: string }[];
  tags: string[];
}

/** A node in the knowledge graph */
export type KnowledgeGraphNode = Node<GraphNodeData, GraphNodeType>;

/** An edge in the knowledge graph */
export type KnowledgeGraphEdge = Edge<{ label: string; edgeType: string }>;

/** Detail shown in the right panel when a node is selected */
export interface NodeDetail {
  nodeId: string;
  label: string;
  nodeType: GraphNodeType;
  category: string;
  properties: { key: string; value: string }[];
  tags: string[];
  relationships: { target: string; label: string; direction: "out" | "in" }[];
}
