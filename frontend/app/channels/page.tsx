'use client';

import { useCallback, useEffect, useState } from 'react';
import AppShell from '@/components/AppShell';
import {
  channelsApi,
  type ChannelHealth,
  type ChannelOrder,
  type ChannelOverview,
  type ChannelPlatform,
  type ChannelProducts,
  type ChannelSource,
  type ChannelStock,
} from '@/lib/channelsApi';

const PLATFORMS: { key: ChannelPlatform; label: string; order: string; hint: string }[] = [
  { key: 'shopee', label: 'Shopee', order: '231022SPE001', hint: '订单号形如 231022SPE001' },
  { key: 'shopify', label: 'Shopify', order: '#1001', hint: '订单号形如 #1001' },
];

const DEFAULT_SKU = 'SKU-P1004-42';

const SOURCE_STYLE: Record<ChannelSource, { label: string; className: string }> = {
  'shopee-mock': { label: 'Shopee Mock', className: 'bg-indigo-50 text-indigo-600' },
  'shopee-sandbox': { label: 'Shopee 沙箱', className: 'bg-cyan-50 text-cyan-700' },
  'shopee-live': { label: 'Shopee Live', className: 'bg-emerald-50 text-emerald-600' },
  'shopify-mock': { label: 'Shopify Mock', className: 'bg-indigo-50 text-indigo-600' },
  'shopify-live': { label: 'Shopify Live', className: 'bg-emerald-50 text-emerald-600' },
  'channel-cache': { label: '渠道快照 · 已回放', className: 'bg-sky-50 text-sky-700' },
  local: { label: '本地库', className: 'bg-slate-100 text-slate-600' },
  'local-fallback': { label: '渠道故障 · 已降级', className: 'bg-amber-50 text-amber-600' },
};

const MODE_STYLE: Record<string, string> = {
  mock: 'bg-indigo-50 text-indigo-600',
  sandbox: 'bg-cyan-50 text-cyan-700',
  live: 'bg-emerald-50 text-emerald-600',
  local: 'bg-slate-100 text-slate-600',
};

function SourceBadge({ source }: { source: ChannelSource }) {
  const style = SOURCE_STYLE[source] ?? SOURCE_STYLE.local;
  return (
    <span className={`rounded-[2px] px-2 py-0.5 text-[11px] font-medium ${style.className}`}>
      {style.label}
    </span>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10.5px] uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-0.5 font-mono text-[11.5px] text-slate-700">{value}</div>
    </div>
  );
}

export default function ChannelsPage() {
  const [active, setActive] = useState<ChannelPlatform>('shopee');
  const [overview, setOverview] = useState<ChannelOverview | null>(null);
  const [health, setHealth] = useState<Partial<Record<ChannelPlatform, ChannelHealth>>>({});
  const [healthError, setHealthError] = useState<string | null>(null);

  const [orderNo, setOrderNo] = useState(PLATFORMS[0].order);
  const [order, setOrder] = useState<ChannelOrder | null>(null);
  const [orderError, setOrderError] = useState<string | null>(null);

  const [sku, setSku] = useState(DEFAULT_SKU);
  const [stock, setStock] = useState<ChannelStock | null>(null);
  const [stockError, setStockError] = useState<string | null>(null);

  const [products, setProducts] = useState<ChannelProducts | null>(null);
  const [productsError, setProductsError] = useState<string | null>(null);

  const [busy, setBusy] = useState<'health' | 'order' | 'stock' | 'products' | null>(null);

  const current = PLATFORMS.find((p) => p.key === active) ?? PLATFORMS[0];

  const loadHealth = useCallback(async (platform: ChannelPlatform) => {
    try {
      setHealthError(null);
      const data = await channelsApi.health(platform);
      setHealth((prev) => ({ ...prev, [platform]: data }));
    } catch (e) {
      setHealthError(e instanceof Error ? e.message : '自检失败');
    }
  }, []);

  const loadOrder = useCallback(async (platform: ChannelPlatform, value: string) => {
    const no = value.trim();
    if (!no) return;
    setBusy('order');
    setOrderError(null);
    try {
      setOrder(await channelsApi.order(platform, no));
    } catch (e) {
      setOrder(null);
      setOrderError(e instanceof Error ? e.message : '订单查询失败');
    } finally {
      setBusy(null);
    }
  }, []);

  const loadStock = useCallback(async (platform: ChannelPlatform, value: string) => {
    const code = value.trim();
    if (!code) return;
    setBusy('stock');
    setStockError(null);
    try {
      setStock(await channelsApi.stock(platform, code));
    } catch (e) {
      setStock(null);
      setStockError(e instanceof Error ? e.message : '库存查询失败');
    } finally {
      setBusy(null);
    }
  }, []);

  const loadProducts = useCallback(async (platform: ChannelPlatform) => {
    setBusy('products');
    setProductsError(null);
    try {
      setProducts(await channelsApi.products(platform));
    } catch (e) {
      setProducts(null);
      setProductsError(e instanceof Error ? e.message : '商品拉取失败');
    } finally {
      setBusy(null);
    }
  }, []);

  const refreshAll = useCallback(async () => {
    setBusy('health');
    try {
      setOverview(await channelsApi.overview());
    } catch (e) {
      setHealthError(e instanceof Error ? e.message : '渠道概览加载失败');
    }
    await Promise.all([
      loadHealth('shopee'),
      loadHealth('shopify'),
      loadOrder(active, orderNo),
      loadStock(active, sku),
      loadProducts(active),
    ]);
    setBusy(null);
  }, [active, orderNo, sku, loadHealth, loadOrder, loadStock, loadProducts]);

  useEffect(() => {
    void (async () => {
      try {
        setOverview(await channelsApi.overview());
      } catch {
        // 概览失败不阻断页面，下面两个 health 会给出具体原因
      }
      await Promise.all([loadHealth('shopee'), loadHealth('shopify')]);
    })();
  }, [loadHealth]);

  // 切换平台时重置查询条件与结果，避免把 Shopee 的订单号打到 Shopify 上
  useEffect(() => {
    const preset = PLATFORMS.find((p) => p.key === active) ?? PLATFORMS[0];
    setOrderNo(preset.order);
    setOrder(null);
    setOrderError(null);
    setStock(null);
    setStockError(null);
    setProducts(null);
    setProductsError(null);
    void loadOrder(active, preset.order);
    void loadStock(active, DEFAULT_SKU);
    void loadProducts(active);
    // 仅在平台切换时触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  return (
    <AppShell>
      <div className="mx-auto w-full max-w-[1180px]">
        <header className="flex flex-wrap items-end justify-between gap-3 border-b border-rule border-t-[3px] border-t-ink-900 pb-3 pt-3">
          <div>
            <div className="mono-label text-muted">Integrations / 渠道适配层</div>
            <h1 className="mt-1.5 text-[26px] leading-tight text-slate-900 md:text-[30px]">
              渠道集成
            </h1>
            <p className="mt-1 text-[13px] text-slate-600">
              Shopee Open API v2 / Shopify Admin API 只读接入：签名、字段映射、分页限流与故障降级。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-[2px] bg-paper-3 px-2.5 py-1 text-[11.5px] font-medium text-slate-600 hairline">
              CHANNEL_MODE={overview?.default_mode ?? '—'}
            </span>
            <button
              onClick={() => void refreshAll()}
              disabled={busy !== null}
              className="press rounded-[2px] bg-accent px-3.5 py-1.5 text-[12px] font-medium text-accent-ink hover:bg-accent-hi disabled:opacity-60"
            >
              {busy ? '刷新中' : '重新自检'}
            </button>
          </div>
        </header>

        {healthError && (
          <div className="mt-3 rounded-[2px] bg-rose-50/80 px-3 py-2 text-[12px] text-rose-600">
            {healthError}
          </div>
        )}

        {/* 平台概览：点击切换当前查询平台 */}
        <div className="mt-4 grid grid-cols-1 gap-3.5 md:grid-cols-2">
          {PLATFORMS.map((p) => {
            const info = health[p.key];
            const isActive = p.key === active;
            return (
              <button
                key={p.key}
                onClick={() => setActive(p.key)}
                className={`press rounded-[2px] bg-paper-2 p-4 text-left shadow-lift transition ${
                  isActive ? 'ring-1 ring-ink-900' : 'hover:bg-paper-3/60'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-[15px] font-semibold text-slate-900">{p.label}</span>
                  <span
                    className={`rounded-[2px] px-2 py-0.5 text-[11px] font-medium ${
                      MODE_STYLE[info?.mode ?? ''] ?? 'bg-paper-3 text-slate-500'
                    }`}
                  >
                    {info?.mode ?? '检测中'}
                  </span>
                  <span
                    className={`ml-auto rounded-[2px] px-2 py-0.5 text-[11px] font-medium ${
                      info?.ok
                        ? 'bg-emerald-50 text-emerald-600'
                        : info
                          ? 'bg-amber-50 text-amber-600'
                          : 'bg-paper-3 text-slate-500'
                    }`}
                  >
                    {info ? (info.ok ? '连通' : '不可用') : '检测中'}
                  </span>
                </div>
                <div className="mt-2 text-[12px] text-slate-500">
                  {info?.adapter ?? '—'}
                  {typeof info?.latency_ms === 'number' && ` · ${info.latency_ms}ms`}
                </div>
                <div className="mt-1 line-clamp-2 min-h-[18px] text-[11.5px] text-slate-400">
                  {info?.error || info?.probe?.note || info?.note || '—'}
                </div>
              </button>
            );
          })}
        </div>

        <div className="mt-3.5 grid grid-cols-1 gap-3.5 lg:grid-cols-3">
          {/* 左：订单 + 库存 */}
          <div className="flex flex-col gap-3.5 lg:col-span-2">
            <section className="rounded-[2px] bg-paper-2 p-4 shadow-lift md:p-5">
              <div className="flex items-center justify-between">
                <div className="text-[13.5px] font-semibold text-slate-800">
                  {current.label} 订单查询
                </div>
                <span className="font-mono text-[11px] text-slate-400">
                  GET /api/channels/{active}/orders/{'{order_no}'}
                </span>
              </div>
              <form
                className="mt-2.5 flex items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void loadOrder(active, orderNo);
                }}
              >
                <input
                  value={orderNo}
                  onChange={(e) => setOrderNo(e.target.value)}
                  placeholder={current.hint}
                  className="min-w-0 flex-1 rounded-[2px] bg-canvas px-3 py-1.5 font-mono text-[12px] text-slate-800 outline-none hairline focus:border-ink-900"
                />
                <button
                  type="submit"
                  disabled={busy === 'order'}
                  className="press shrink-0 rounded-[2px] bg-ink px-3 py-1.5 text-[12px] font-medium text-paper-2 disabled:opacity-60"
                >
                  {busy === 'order' ? '查询中…' : '查询'}
                </button>
              </form>

              {orderError && (
                <div className="mt-2.5 rounded-[2px] bg-rose-50/80 px-3 py-2 text-[12px] text-rose-600">
                  {orderError}
                </div>
              )}

              {order && (
                <div className="mt-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[13px] font-semibold text-slate-900">
                      {order.order_no}
                    </span>
                    <span className="rounded-[2px] bg-paper-3 px-2 py-0.5 text-[11px] text-slate-600">
                      {order.status_text}
                    </span>
                    <SourceBadge source={order.source} />
                    <span className="ml-auto text-[12px] text-slate-600">
                      {order.total_amount.toFixed(2)}
                      {order.discount_amount > 0 && (
                        <span className="ml-1 text-slate-400">
                          （优惠 {order.discount_amount.toFixed(2)}）
                        </span>
                      )}
                    </span>
                  </div>

                  <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 md:grid-cols-4">
                    <Meta label="支付方式" value={order.pay_method || '—'} />
                    <Meta label="下单时间" value={order.created_at || '—'} />
                    <Meta label="支付时间" value={order.paid_at || '—'} />
                    <Meta label="发货时间" value={order.shipped_at || '—'} />
                  </div>
                  {order.address && (
                    <div className="mt-1.5 text-[12px] text-slate-500">收货地址：{order.address}</div>
                  )}

                  <div className="nice-scroll mt-2.5 overflow-x-auto">
                    <table className="w-full min-w-[480px] border-separate border-spacing-y-1 text-left text-[12px]">
                      <thead>
                        <tr className="text-[11px] font-medium text-slate-400">
                          <th className="px-2 pb-1">商品</th>
                          <th className="px-2 pb-1">尺码</th>
                          <th className="px-2 pb-1 text-right">数量</th>
                          <th className="px-2 pb-1 text-right">单价</th>
                        </tr>
                      </thead>
                      <tbody>
                        {order.items.map((item, idx) => (
                          <tr key={`${item.product_id}-${idx}`} className="bg-canvas/70">
                            <td className="rounded-l-[2px] px-2 py-1.5 text-slate-700">
                              {item.product_name}
                            </td>
                            <td className="px-2 py-1.5 font-mono text-slate-500">{item.size || '—'}</td>
                            <td className="px-2 py-1.5 text-right tabular-nums text-slate-600">
                              {item.qty}
                            </td>
                            <td className="rounded-r-[2px] px-2 py-1.5 text-right tabular-nums text-slate-700">
                              {item.unit_price.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {order.note && (
                    <div className="mt-2 text-[11.5px] text-amber-600">降级说明：{order.note}</div>
                  )}
                </div>
              )}
            </section>

            <section className="rounded-[2px] bg-paper-2 p-4 shadow-lift md:p-5">
              <div className="flex items-center justify-between">
                <div className="text-[13.5px] font-semibold text-slate-800">SKU 库存</div>
                <span className="font-mono text-[11px] text-slate-400">
                  GET /api/channels/{active}/stock/{'{sku}'}
                </span>
              </div>
              <form
                className="mt-2.5 flex items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void loadStock(active, sku);
                }}
              >
                <input
                  value={sku}
                  onChange={(e) => setSku(e.target.value)}
                  placeholder="SKU，如 SKU-P1004-42"
                  className="min-w-0 flex-1 rounded-[2px] bg-canvas px-3 py-1.5 font-mono text-[12px] text-slate-800 outline-none hairline focus:border-ink-900"
                />
                <button
                  type="submit"
                  disabled={busy === 'stock'}
                  className="press shrink-0 rounded-[2px] bg-ink px-3 py-1.5 text-[12px] font-medium text-paper-2 disabled:opacity-60"
                >
                  {busy === 'stock' ? '查询中…' : '查询'}
                </button>
              </form>

              {stockError && (
                <div className="mt-2.5 rounded-[2px] bg-rose-50/80 px-3 py-2 text-[12px] text-rose-600">
                  {stockError}
                </div>
              )}

              {stock && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[13px] font-semibold text-slate-900">{stock.sku}</span>
                  <span className="rounded-[2px] bg-paper-3 px-2 py-0.5 text-[11px] text-slate-600">
                    {stock.product_id} · {stock.size}
                  </span>
                  <SourceBadge source={stock.source} />
                  <span
                    className={`ml-auto text-[13px] font-semibold tabular-nums ${
                      stock.low_stock ? 'text-amber-600' : 'text-emerald-600'
                    }`}
                  >
                    {stock.available} 件
                    {stock.low_stock && <span className="ml-1 text-[11px] font-normal">偏低</span>}
                  </span>
                </div>
              )}
              {stock && (
                <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 md:grid-cols-3">
                  <Meta label="颜色" value={stock.color || '—'} />
                  <Meta label="仓库" value={stock.warehouse} />
                  <Meta label="占用" value={String(stock.reserved)} />
                </div>
              )}
              {stock?.note && (
                <div className="mt-2 text-[11.5px] text-amber-600">降级说明：{stock.note}</div>
              )}
            </section>
          </div>

          {/* 右：商品主数据 + 映射说明 */}
          <div className="flex flex-col gap-3.5">
            <section className="rounded-[2px] bg-paper-2 p-4 shadow-lift">
              <div className="flex items-center justify-between">
                <div className="text-[13.5px] font-semibold text-slate-800">商品主数据</div>
                <button
                  onClick={() => void loadProducts(active)}
                  disabled={busy === 'products'}
                  className="press rounded-[2px] bg-paper-3 px-2.5 py-1 text-[11.5px] text-slate-700 hover:bg-paper-3/70 disabled:opacity-60"
                >
                  {busy === 'products' ? '同步中…' : '重新拉取'}
                </button>
              </div>
              <div className="mt-1 font-mono text-[11px] text-slate-400">
                GET /api/channels/{active}/products
              </div>

              {productsError && (
                <div className="mt-2.5 rounded-[2px] bg-rose-50/80 px-3 py-2 text-[12px] text-rose-600">
                  {productsError}
                </div>
              )}

              {products && (
                <>
                  <div className="mt-2 flex items-center gap-2">
                    <SourceBadge source={products.source} />
                    <span className="text-[11.5px] text-slate-500">{products.count} 条</span>
                  </div>
                  <div className="nice-scroll mt-2 max-h-[292px] overflow-y-auto">
                    <table className="w-full text-left text-[12px]">
                      <tbody>
                        {products.items.map((p) => (
                          <tr key={p.product_id} className="border-b border-rule/60 last:border-0">
                            <td className="py-1.5 pr-2 text-slate-700">{p.name}</td>
                            <td className="py-1.5 text-right tabular-nums text-slate-600">
                              {p.currency} {p.price.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
              {products?.note && (
                <div className="mt-2 text-[11.5px] text-amber-600">降级说明：{products.note}</div>
              )}
            </section>

            <section className="rounded-[2px] bg-paper-2 p-4 shadow-lift">
              <div className="text-[13.5px] font-semibold text-slate-800">平台 → 内部字段</div>
              <ul className="mt-2 space-y-1.5 text-[12px] leading-relaxed text-slate-600">
                <li>
                  <span className="font-mono text-[11.5px] text-slate-800">order_sn / name</span>
                  {' → '}order_no
                </li>
                <li>
                  <span className="font-mono text-[11.5px] text-slate-800">order_status / financial + fulfillment</span>
                  {' → '}status
                </li>
                <li>
                  <span className="font-mono text-[11.5px] text-slate-800">item_list / line_items</span>
                  {' → '}items
                </li>
                <li>
                  <span className="font-mono text-[11.5px] text-slate-800">model_sku / variants.sku</span>
                  {' → '}库存 SKU
                </li>
                <li>
                  <span className="font-mono text-[11.5px] text-slate-800">unix / ISO 时间</span>
                  {' → '}东八区 `YYYY-MM-DD HH:MM`
                </li>
              </ul>
              <p className="mt-2.5 border-t border-rule pt-2 text-[11.5px] leading-relaxed text-slate-400">
                渠道成功结果按租户写入 channel_snapshots；失败时先回放最近快照（channel-cache），
                再回落本地 MySQL（local-fallback），不把兜底数据伪装成平台结果。
              </p>
            </section>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
