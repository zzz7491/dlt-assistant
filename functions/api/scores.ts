/**
 * GET /api/scores - 大乐透综合评分缓存查询（只读 API，轨 B）
 *
 * 数据来源：Cloudflare D1 `dlt_scores`（binding: DB，经 wrangler.toml 配置）
 * 参数：
 *   period       = 50 | 100 | 300 | 1000 | all   （默认 all；all 映射 D1 period=0 全历史）
 *   kind         = front | back                  （默认 front）
 *   model_type   = standard | cold-hot | expert  （默认 standard）
 *   weight_version = default                     （默认 default）
 * 排序：ORDER BY total DESC, num ASC
 * 返回：{ period, kind, model_type, weight_version, computed_at, numbers[{num,total,parts,tag}] }
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

interface ScoreRow {
  num: number;
  total: number;
  parts: string;
  tag: string;
  computed_at: string;
}

const PERIODS = ["50", "100", "300", "1000", "all"] as const;
const KINDS = ["front", "back"] as const;
const MODEL_TYPES = ["standard", "cold-hot", "expert"] as const;
const WEIGHT_RE = /^[a-zA-Z0-9_-]{1,32}$/;

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
    const modelType = url.searchParams.get("model_type") ?? "standard";
    const weightVersion = url.searchParams.get("weight_version") ?? "default";

    // 参数白名单校验（防注入 + 明确报错）
    if (!PERIODS.includes(period as (typeof PERIODS)[number])) {
      return json({ error: "invalid period" }, 400);
    }
    if (!KINDS.includes(kind as (typeof KINDS)[number])) {
      return json({ error: "invalid kind" }, 400);
    }
    if (!MODEL_TYPES.includes(modelType as (typeof MODEL_TYPES)[number])) {
      return json({ error: "invalid model_type" }, 400);
    }
    if (!WEIGHT_RE.test(weightVersion)) {
      return json({ error: "invalid weight_version" }, 400);
    }

    // all → D1 period=0（全历史）
    const periodValue = period === "all" ? 0 : Number(period);

    const sql = `
      SELECT num, total, parts, tag, computed_at
      FROM dlt_scores
      WHERE period = ? AND kind = ? AND model_type = ? AND weight_version = ?
      ORDER BY total DESC, num ASC
    `;
    const { results } = await env.DB.prepare(sql)
      .bind(periodValue, kind, modelType, weightVersion)
      .all<ScoreRow>();

    // parts 为 JSON 文本，自动解析；解析失败保留原文本（不中断）
    const numbers = results.map((r) => {
      let parts: unknown = r.parts;
      try {
        parts = JSON.parse(r.parts);
      } catch {
        /* keep raw string */
      }
      return {
        num: r.num,
        total: r.total,
        parts,
        tag: r.tag,
      };
    });

    const body = {
      period: periodValue,
      kind,
      model_type: modelType,
      weight_version: weightVersion,
      computed_at: results.length ? results[0].computed_at : "",
      numbers,
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
