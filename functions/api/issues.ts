/**
 * GET /api/issues - 大乐透历史开奖数据查询（只读 API）
 *
 * 数据来源：Cloudflare D1 `dlt-draws`（binding: DB，经 wrangler.toml 配置）
 * 参数：
 *   range = 50 | 1000 | all   （默认 50；非法值返回 400）
 * 排序：ORDER BY issue_num DESC（issue 为 TEXT，issue_num 为 INTEGER，避免字符串期号排序错误）
 * 返回：与 public/data/dlt_history.json 同构 {updated_at, source, count, issues[]}
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
  all<T = unknown>(): Promise<{ results: T[] }>;
}

interface DrawRow {
  issue: string;
  date: string;
  front1: number;
  front2: number;
  front3: number;
  front4: number;
  front5: number;
  back1: number;
  back2: number;
  updated_at: string | null;
}

const ALLOWED_RANGES = ["50", "1000", "all"] as const;
const DEFAULT_RANGE = "50";

export const onRequestGet = async ({
  env,
  request,
}: {
  env: Env;
  request: Request;
}): Promise<Response> => {
  try {
    const url = new URL(request.url);
    const range = url.searchParams.get("range") ?? DEFAULT_RANGE;

    if (!ALLOWED_RANGES.includes(range as (typeof ALLOWED_RANGES)[number])) {
      return json({ error: "invalid range" }, 400);
    }

    // 构建 SQL：按 issue_num DESC；all 不限制行数，其余 LIMIT
    const limitClause = range === "all" ? "" : `LIMIT ${range}`;
    const sql = `
      SELECT issue, date, front1, front2, front3, front4, front5, back1, back2, updated_at
      FROM dlt_draws
      ORDER BY issue_num DESC
      ${limitClause}
    `;

    const { results } = await env.DB.prepare(sql).all<DrawRow>();

    const issues = results.map((r) => ({
      issue: r.issue,
      date: r.date,
      front: [r.front1, r.front2, r.front3, r.front4, r.front5],
      back: [r.back1, r.back2],
    }));

    const body = {
      updated_at: results.length ? (results[0].updated_at ?? "") : "",
      source: "500",
      count: issues.length,
      issues,
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
