/**
 * GET /api/analysis - 大乐透分析指标缓存查询（只读 API，轨 B）
 *
 * 数据来源：Cloudflare D1 `dlt_analysis`（binding: DB，经 wrangler.toml 配置）
 * 参数：
 *   period = 50 | 100 | 300 | 1000 | all   （默认 all；all 映射 D1 period=0 全历史）
 *   kind   = front | back                  （默认 front）
 *   metric = frequency | hot | missing | oddEven | bigSmall | consec   （可选）
 *
 * 返回：
 *   - 未指定 metric：{ period, kind, metrics: [{metric, version, payload, computed_at}, ...] }
 *   - 指定 metric：  { period, kind, metric, version, payload, computed_at }
 *
 * 约束：只读、无认证、不写数据库、不创建表、不含中奖概率/预测字段。
 */

// 最小类型声明（不依赖 @cloudflare/workers-types，便于本地 tsc 校验）
interface Env {
  DB: D1Database;
}
interface D1Database {
  prepare(sql: string): D1PreparedStatement;
}
interface D1PreparedStatement {
  bind(...values: unknown[]): D1PreparedStatement;
  all<T = unknown>(): Promise<{ results: T[] }>;
}

interface AnalysisRow {
  metric: string;
  version: string;
  payload: string;
  computed_at: string;
}

const PERIODS = ["50", "100", "300", "1000", "all"] as const;
const KINDS = ["front", "back"] as const;
const METRICS = [
  "frequency",
  "hot",
  "missing",
  "oddEven",
  "bigSmall",
  "consec",
] as const;

export const onRequestGet = async ({
  env,
  request,
}: {
  env: Env;
  request: Request;
}): Promise<Response> => {
  try {
    const url = new URL(request.url);
    const period = url.searchParams.get("period") ?? "all";
    const kind = url.searchParams.get("kind") ?? "front";
    const metric = url.searchParams.get("metric") ?? "";

    // 参数白名单校验
    if (!PERIODS.includes(period as (typeof PERIODS)[number])) {
      return json({ error: "invalid period" }, 400);
    }
    if (!KINDS.includes(kind as (typeof KINDS)[number])) {
      return json({ error: "invalid kind" }, 400);
    }
    if (metric !== "" && !METRICS.includes(metric as (typeof METRICS)[number])) {
      return json({ error: "invalid metric" }, 400);
    }

    // all → D1 period=0（全历史）
    const periodValue = period === "all" ? 0 : Number(period);

    let sql: string;
    let rows: AnalysisRow[];
    if (metric === "") {
      sql = `
        SELECT metric, version, payload, computed_at
        FROM dlt_analysis
        WHERE period = ? AND kind = ?
        ORDER BY metric ASC
      `;
      ({ results: rows } = await env.DB.prepare(sql)
        .bind(periodValue, kind)
        .all<AnalysisRow>());
    } else {
      sql = `
        SELECT metric, version, payload, computed_at
        FROM dlt_analysis
        WHERE period = ? AND kind = ? AND metric = ?
      `;
      ({ results: rows } = await env.DB.prepare(sql)
        .bind(periodValue, kind, metric)
        .all<AnalysisRow>());
    }

    // payload 为 JSON 文本，自动解析；失败保留原文本
    const parsePayload = (raw: string): unknown => {
      try {
        return JSON.parse(raw);
      } catch {
        return raw;
      }
    };

    if (metric === "") {
      const body = {
        period: periodValue,
        kind,
        metrics: rows.map((r) => ({
          metric: r.metric,
          version: r.version,
          payload: parsePayload(r.payload),
          computed_at: r.computed_at,
        })),
      };
      return json(body, 200);
    }

    const row = rows[0];
    const body = {
      period: periodValue,
      kind,
      metric: row ? row.metric : metric,
      version: row ? row.version : "",
      payload: row ? parsePayload(row.payload) : null,
      computed_at: row ? row.computed_at : "",
    };
    return json(body, 200);
  } catch (err) {
    return json(
      { error: err instanceof Error ? err.message : String(err) },
      500,
    );
  }
};

function json(data: unknown, status: number): Response {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300",
    },
  });
}
