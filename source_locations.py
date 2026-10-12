import re
def locate_value(blocks,observation):
    def clean(s):return re.sub(r'^[\d.▲★*\s]+','',re.sub(r'[（(].*?[）)]','',s)).strip()
    anchors=[b for b in blocks if observation.get('code') and b['text']==observation['code']]
    if not anchors:
        name=clean(observation['name'])
        anchors=[b for b in blocks if name and clean(b['text'])==name]
    values=[b for b in blocks if b['text']==observation['value']]
    pairs=[]
    for a in anchors:
        ay=(a['box'][1]+a['box'][3])/2
        for v in values:
            vy=(v['box'][1]+v['box'][3])/2
            if abs(ay-vy)<(a['box'][3]-a['box'][1])*.8 and v['box'][0]>a['box'][0]:pairs.append((abs(ay-vy),v['box']))
    if pairs:return min(pairs,key=lambda p:p[0])[1]
    return values[0]['box'] if len(values)==1 else []
