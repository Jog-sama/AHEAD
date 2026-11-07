export async function GET({query}) {
  return await query('SELECT * FROM hazards ORDER BY observed_at DESC LIMIT 250');
}
