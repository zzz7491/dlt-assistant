/**
 * GET /api/summary - 大乐透历史数据中心摘要（只读 API）
 *
 * 数据来源：Cloudflare D1 `dlt-draws`（binding: DB，经 wrangler.toml 配置）
 * 返回：总期数 / 最早期号 / 最新期号 / 最早日期 / 最新日期 / 数据更新时间
 * 约束：只读、无认证、不写数据库、不创建表。
 */

// 最小类型声明（不依赖 @cloudflare/workers-types，便于本地 tsc 校验）
interface Env {
  DB: D1Database;
}
interface D1Database {
  prepare(sql: string): D1PreparedStatement;
}
interface D1PreparedStatement {
  first<T = unknown>(): Promise<T | null>;
}

interface SummaryRow {
  count: number;
  first_issue: string;
  last_issue: string;
  first_date: string;
  last_date: string;
  updated_at: string | null;
}

export const onRequestGet = async ({ env }: { env: Env }): Promise<Response> => {
  try {
    // 首末按期号数值（issue_num）排序，避免字符串期号排序风险
    const sql = `
      SELECT
        COUNT(*) AS count,
        (SELECT issue FROM dlt_draws ORDER BY issue_num ASC  LIMIT 1) AS first_issue,
        (SELECT issue FROM dlt_draws ORDER BY issue_num DESC LIMIT 1) AS last_issue,
        (SELECT date   FROM dlt_draws ORDER BY issue_num ASC  LIMIT 1) AS first_date,
        (SELECT date   FROM dlt_draws ORDER BY issue_num DESC LIMIT 1) AS last_date,
        MAX(updated_at) AS updated_at
      FROM dlt_draws
    `;
    const row = (await env.DB.prepare(sql).first()) as SummaryRow | null;

    const body = {
      source: "500",
      count: row?.count ?? 0,
      first_issue: row?.first_issue ?? "",
      last_issue: row?.last_issue ?? "",
      first_date: row?.first_date ?? "",
      last_date: row?.last_date ?? "",
      updated_at: row?.updated_at ?? "",
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
