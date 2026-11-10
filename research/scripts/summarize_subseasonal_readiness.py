"""Build concise availability tables from the saved, bounded audit evidence."""
import csv
import datetime as dt
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'research/audits/subseasonal-readiness'
read=lambda name:json.loads((AUDIT/name).read_text())

def write_csv(name,rows):
    with (AUDIT/name).open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def main():
    pairs={}
    for item in read('model-grids.json')['probes']:
        pairs.setdefault(item['name'],{})[item['kind']]=item
    gefs={}
    for item in read('coordinates.json')['probes']:
        coords=item['coordinates']
        item=dict(item,dimensions={k:len(v) for k,v in coords.items()},
            coordinate_metadata={k:{'min':min(v),'max':max(v),'first':v[:3],'last':v[-3:]} for k,v in coords.items()})
        gefs[item['kind']]=item
    pairs={'GEFSv12_CPC_SubX':gefs,**pairs}
    models=[];leads=[]
    for name,pair in pairs.items():
        hc,fc=pair.get('hindcast',{}),pair.get('forecast',{})
        def dates(item):return [value[:10] for value in item.get('start_range',['unresolved','unresolved'])]
        hdates,fdates=dates(hc),dates(fc)
        x=hc.get('coordinate_metadata',{}).get('X',{}).get('first',[]) or fc.get('coordinate_metadata',{}).get('X',{}).get('first',[])
        spacing=round(abs(x[1]-x[0]),6) if len(x)>1 else None
        models.append({'model':name,'hindcast_start':hdates[0],'hindcast_end':hdates[1],
            'hindcast_start_slots':hc.get('dimensions',{}).get('S'),
            'hindcast_member_slots':hc.get('dimensions',{}).get('M'),
            'forecast_start':fdates[0],'forecast_end':fdates[1],
            'forecast_member_slots':fc.get('dimensions',{}).get('M'),
            'native_grid_degrees':spacing,
            'hindcast_lead_slots':hc.get('dimensions',{}).get('L'),
            'forecast_lead_slots':fc.get('dimensions',{}).get('L'),
            'installed_subseasonal_template':name=='GEFSv12_CPC_SubX',
            'hindcast_metadata_status':hc.get('status'),'forecast_metadata_status':fc.get('status')})
        for kind,item in pair.items():
            axis=item.get('coordinates',{}).get('L')
            if axis is None:
                info=item.get('coordinate_metadata',{}).get('L')
                if info and item['dimensions']['L']>1:
                    # Confirmed regular 1-day L grid from first/last triples.
                    assert info['first'][1]-info['first'][0]==1
                    assert info['last'][-1]-info['last'][-2]==1
                    axis=[info['min']+i for i in range(item['dimensions']['L'])]
            for week in range(1,5):
                low,high=1+7*(week-1),7*week
                expected=[low+0.5+i for i in range(7)]
                count=sum(v in axis for v in expected) if axis is not None else None
                leads.append({'model':name,'kind':kind,'week':week,'first_calendar_offset':low,
                    'last_calendar_offset_inclusive':high,'expected_midpoint_first':low+0.5,
                    'expected_midpoint_last':high+0.5,'lead_slots_found':count,'all_seven_slots_present':count==7})
    write_csv('model-availability.csv',models);write_csv('weekly-lead-slots.csv',leads)
    obs=read('daily-observations.json')['annual_listings'];daily=[]
    for variant in ['rnl','sat']:
        rows=[r for r in obs if r['variant']==variant]
        full=[r['year'] for r in rows if r['daily_tiff_files']>0 and not r['missing_dates']]
        actual=[r for r in rows if r['daily_tiff_files']>0]
        daily.append({'product':'CHIRPS3 final '+variant,'first_complete_year':min(full),'last_complete_year':max(full),
            'complete_years':len(full),'latest_file_date':max(r['last'] for r in actual),
            'indexed_daily_files':sum(r['daily_tiff_files'] for r in rows),'daily_pixels_all_dates_checked':False})
    write_csv('daily-observation-availability.csv',daily)
    report_table=['| Archive/model | Hindcast coordinate range | HC members* | Forecast coordinate range | FC members* | Native grid |',
                  '| --- | --- | ---: | --- | ---: | ---: |']
    for r in models:
        h='unresolved' if r['hindcast_start']=='unresolved' else f"{r['hindcast_start']}–{r['hindcast_end']}"
        f='unresolved' if r['forecast_start']=='unresolved' else f"{r['forecast_start']}–{r['forecast_end']}"
        grid=f"{r['native_grid_degrees']}°" if r['native_grid_degrees'] else '—'
        report_table.append(f"| {r['model'].replace('_SubX','')} | {h} | {r['hindcast_member_slots'] or '—'} | {f} | {r['forecast_member_slots'] or '—'} | {grid} |")
    (AUDIT/'model-table.md').write_text('\n'.join(report_table)+'\n')
    record={'date':'2026-11-02','subx_model_version_entries':len(models),
        'subx_provider_directories':8,'s2s_provider_directories':12,
        'model_branch_coordinate_profiles':sum('coordinate_metadata' in p or 'coordinates' in p for pair in pairs.values() for p in pair.values()),
        'weekly_convention':'Provisional prototype convention: calendar dates init+1..7, +8..14, +15..21, +22..28; end inclusive. Lead coordinates alone do not validate precipitation accumulation intervals.',
        'model_case_selected':False,'training_period_selected':False,'fits_run':0,
        'model_pixel_continuity_all_dates_verified':False,'observation_pixel_continuity_all_dates_verified':False,
        'workflow_status':'Requires a separate audited preparation/downloader adapter; installed subseasonal driver not ready unchanged.',
        'tables':['model-availability.csv','weekly-lead-slots.csv','daily-observation-availability.csv']}
    (AUDIT/'summary.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))

if __name__=='__main__':main()
