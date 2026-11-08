#!/usr/bin/env python3
"""Metrics from the Ahead page's CSV log plus a ground-truth file.

usage: analyze.py walk.csv [obstacles.csv]
walk.csv: the page's "Copy log" output (t_s,event,walking,state,dist_m,band,col[,battery,thermal...]).
obstacles.csv: position_m,name — metres from the start, measured once on the route. Positions are matched
to the log by walked distance; the page logs distance only in 'steps' rows if present, else by time at
constant speed (pass --speed m/s). Without obstacles.csv only alert counts, rate and losses are reported.
"""
import csv, sys, statistics

def load(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    speed = next((float(a.split('=')[1]) for a in sys.argv if a.startswith('--speed=')), None)
    if not args: sys.exit(__doc__)
    rows = load(args[0])
    obstacles = load(args[1]) if len(args) > 1 else []
    t_end = float(rows[-1]['t_s']) if rows else 0
    alerts = [r for r in rows if r['event'] == 'state' and r.get('state') in ('slow', 'fast')]
    escalations = []
    prev = 'far'
    for r in rows:
        if r['event'] != 'state': continue
        s = r.get('state')
        if s in ('slow', 'fast') and (prev == 'far' or (prev == 'slow' and s == 'fast')): escalations.append(r)
        prev = s
    losses = sum(1 for r in rows if r['event'] == 'lost')
    dist_rows = [r for r in rows if r.get('dist_walked_m')]
    walked = float(dist_rows[-1]['dist_walked_m']) if dist_rows else (speed * t_end if speed else None)
    print(f"running time      {t_end/60:.1f} min")
    print(f"escalations       {len(escalations)} (far→slow, slow→fast or far→fast)")
    print(f"depth losses      {losses}")
    if walked:
        print(f"walked            {walked:.0f} m")
        print(f"alerts per 100 m  {len(escalations)/walked*100:.1f}")
    batt = [float(r['battery']) for r in rows if r.get('battery') not in (None, '')]
    if len(batt) >= 2:
        print(f"battery           {batt[0]*100:.0f}% → {batt[-1]*100:.0f}% over {t_end/3600:.2f} h = {(batt[0]-batt[-1])*100/(t_end/3600):.0f}%/h")
    therm = [r['thermal'] for r in rows if r.get('thermal')]
    if therm:
        first = next((r for r in rows if r.get('thermal') and r['thermal'] != 'nominal'), None)
        print(f"thermal           worst {max(therm, key=['nominal','fair','serious','critical'].index)}" + (f", left nominal at {float(first['t_s'])/60:.0f} min" if first else ''))
    if obstacles and walked and speed:
        print("\nper obstacle (time-based matching at constant speed; approximate)")
        leads, missed = [], 0
        for o in obstacles:
            pos = float(o['position_m']); t_obs = pos / speed
            before = [r for r in escalations if 0 <= t_obs - float(r['t_s']) <= 3 / speed and r.get('dist_m')]
            if before:
                lead = float(before[0]['dist_m']); leads.append(lead)
                print(f"  {o['name']:<24} lead {lead:.1f} m")
            else:
                missed += 1; print(f"  {o['name']:<24} MISSED")
        if leads: print(f"median lead       {statistics.median(leads):.1f} m   missed {missed}/{len(obstacles)}")
        false_alerts = len(escalations) - (len(obstacles) - missed)
        print(f"false alerts      {max(false_alerts,0)} → {max(false_alerts,0)/walked*100:.1f} per 100 m")

if __name__ == '__main__': main()
