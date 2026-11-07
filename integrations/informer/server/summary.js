export async function GET({query}) {
  return await query(`SELECT label, simulated, count(*)::integer AS observations
    FROM hazards WHERE observed_at >= now()-interval '7 days'
    GROUP BY label,simulated ORDER BY observations DESC`);
}
