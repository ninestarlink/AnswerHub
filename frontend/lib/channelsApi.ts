/** 渠道集成只读接口（对应 FastAPI /api/channels/*，无需管理员 Token） */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, '') ?? '';

export type ChannelPlatform = 'shopee' | 'shopify';

export type ChannelSource =
  | 'shopee-mock'
  | 'shopee-sandbox'
  | 'shopee-live'
  | 'shopify-mock'
  | 'shopify-live'
  | 'local'
  | 'local-fallback';

export interface ChannelMeta {
  platform: ChannelPlatform;
  label: string;
  mode: string;
}

export interface ChannelOverview {
  default_mode: string;
  platforms: ChannelMeta[];
}

export interface ChannelHealth {
  platform: ChannelPlatform;
  mode: string;
  ok: boolean;
  adapter: string | null;
  latency_ms?: number;
  probe?: {
    shop?: string;
    domain?: string;
    region?: string;
    endpoint?: string;
    api_version?: string;
    items?: number;
    products?: number;
    orders?: number;
    note?: string;
  };
  error?: string;
  note?: string;
}

export interface ChannelOrderItem {
  product_id: string;
  product_name: string;
  size: string;
  qty: number;
  unit_price: number;
}

export interface ChannelOrder {
  order_no: string;
  status: string;
  status_text: string;
  total_amount: number;
  discount_amount: number;
  pay_method?: string | null;
  address?: string | null;
  created_at?: string | null;
  paid_at?: string | null;
  shipped_at?: string | null;
  items: ChannelOrderItem[];
  source: ChannelSource;
  note?: string;
}

export interface ChannelStock {
  sku: string;
  product_id: string;
  size: string;
  color?: string | null;
  available: number;
  reserved: number;
  warehouse: string;
  low_stock: boolean;
  source: ChannelSource;
  note?: string;
}

export interface ChannelProduct {
  product_id: string;
  name: string;
  price: number;
  currency: string;
  category: string;
}

export interface ChannelProducts {
  entity: string;
  count: number;
  items: ChannelProduct[];
  source: ChannelSource;
  note?: string;
}

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: 'no-store' });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') detail = body.detail;
    } catch {
      // 非 JSON 错误体，保留状态码即可
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const channelsApi = {
  overview: () => request<ChannelOverview>('/api/channels'),
  health: (platform: ChannelPlatform) => request<ChannelHealth>(`/api/channels/${platform}/health`),
  order: (platform: ChannelPlatform, orderNo: string) =>
    request<ChannelOrder>(`/api/channels/${platform}/orders/${encodeURIComponent(orderNo)}`),
  stock: (platform: ChannelPlatform, sku: string) =>
    request<ChannelStock>(`/api/channels/${platform}/stock/${encodeURIComponent(sku)}`),
  products: (platform: ChannelPlatform) =>
    request<ChannelProducts>(`/api/channels/${platform}/products`),
};
