import re,sys,json,os
L=os.path.join('literature','war-room')
lua=open(os.path.join(L,'tts','WarRoom_TTS_jotakami_2419016456_strings.lua'),encoding='utf-8',errors='replace').read()
mp=open(os.path.join(L,'warroom-app','references','python-data-legacy','map.py'),encoding='utf-8').read()
i=lua.index('Map = {');m=lua[i:lua.index('Units = {',i)]
ents=re.findall(r"\n        (\w+) = \{(.*?)\n        \}",m,re.S)
assert len(ents)==187,len(ents)
tts={};ef=set();flags={}
for k,b in ents:
    K=k.upper()
    if not re.search(r"eastern\s*=\s*false",b):ef.add(K)
    a=re.search(r"adjacent = \{([^}]*)\}",b)
    for t in (re.findall(r"'([^']+)'",a.group(1)) if a else []):
        t2,f=re.match(r"([a-z]+\d+)([$@#^]?)$",t).groups()
        tts.setdefault(frozenset((K,t2.upper())),set()).add(f)
app=set(frozenset(x) for x in re.findall(r"\{([A-Z]\d+), ([A-Z]\d+)\}",mp[mp.index('NEIGHBORS = ['):]))
ports=set()
for code,body in re.findall(r"\n([A-Z]\d+) = Territory\((.*?)\n\)",mp,re.S):
    for s in re.findall(r"Port\(\s*sea=([A-Z]\d+)",body):ports.add(frozenset((code,s)))
pas=re.findall(r'NarrowSeaPassage\(\s*name="([^"]+)",\s*regions=\{([A-Z]\d+), ([A-Z]\d+)\}',mp,re.S)
tk=set(tts);
def sea(x):return x[0] in 'AIMNP' and x[:2]!='N' or x[0] in 'AIMP'
only_t=sorted(tk-app-ports,key=lambda p:sorted(p));only_a=sorted((app|ports)-tk,key=lambda p:sorted(p))
sub=lambda ps:[p for p in ps if p&ef]
print('TTS pairs',len(tk),'app NEIGHBORS',len(app),'app ports',len(ports),'app passages',len(pas),'EF regions',len(ef))
print('flag legend counts',{f:sum(f in v for v in tts.values()) for f in '$@#^'})
print('\nTTS-only (EF-touching first):')
for p in sub(only_t)+[p for p in only_t if not p&ef]:print(' ','-'.join(sorted(p)),''.join(sorted(tts[p])),'EF' if p&ef else '')
print('\napp-only (EF-touching first):')
for p in sub(only_a)+[p for p in only_a if not p&ef]:print(' ','-'.join(sorted(p)),'port' if p in ports else '','EF' if p&ef else '')
print('\npassages (app):',[(n,a,b,''.join(sorted(tts.get(frozenset((a,b)),{'MISSING'})))) for n,a,b in pas])
if '--json' in sys.argv:json.dump({'ef':sorted(ef),'tts':{'-'.join(sorted(p)):sorted(v) for p,v in tts.items()},'app':sorted('-'.join(sorted(p)) for p in app),'ports':sorted('-'.join(sorted(p)) for p in ports)},open(os.path.join(L,'board_graphs.json'),'w'),indent=1)
