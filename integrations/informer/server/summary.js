export async function GET({query}) {
  const [totals,top,recent]=await Promise.all([
    query(`SELECT count(*)::integer AS clusters,
      coalesce(sum(duplicate_count),0)::integer AS observations,
      count(*) FILTER (WHERE NOT simulated)::integer AS review_candidates,
      count(*) FILTER (WHERE latitude IS NOT NULL)::integer AS mapped
      FROM hazards WHERE observed_at>=now()-interval '7 days'`),
    query(`SELECT label,sum(duplicate_count)::integer AS observations
      FROM hazards WHERE observed_at>=now()-interval '7 days'
      GROUP BY label ORDER BY observations DESC LIMIT 5`),
    query(`SELECT label,simulated,sum(duplicate_count)::integer AS observations
      FROM hazards WHERE observed_at>=now()-interval '7 days'
      GROUP BY label,simulated ORDER BY observations DESC LIMIT 12`),
  ]);
  return {totals:totals[0],top,recent};
}
