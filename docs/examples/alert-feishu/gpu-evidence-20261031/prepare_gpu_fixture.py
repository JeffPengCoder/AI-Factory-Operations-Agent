#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Expose actual isolated-cache observations under a test-only metric prefix."""
from pathlib import Path
import json,xml.etree.ElementTree as E
ROOT=Path(__file__).resolve().parent;RUN=ROOT.name;NS='mosaic-'+RUN
d=json.loads((ROOT/'isolated-dcgm.private.json').read_text());assert d['success'] and d['allEightGpuEccAndRemapUnchanged']
dm=[r for r in d['commands'] if r['argv'][:2]==['dcgmi','dmon']]
assert '95           1            1' in dm[2]['stdout']
assert all('95' not in r['stdout'] for r in [dm[0],dm[-1]])
xml=[r for r in d['commands'] if r['argv']==['nvidia-smi','-q','-x']]
g=E.fromstring(xml[0]['stdout']).find('gpu');uuid=g.findtext('uuid')
dcgm={'runId':RUN,'test_from':'test from Jeff Peng','scope':'GPU telemetry simulation; not a CPU application crash and not a physical GPU defect','evidence_source':'isolated_dcgm_cache_snapshot','liveHardwareCountersWritten':False,'privateEngineAlreadyStopped':d['childExitAfterCleanup']==0,'cacheObservationAt':dm[2]['at'],'GPU':{'index':0,'uuid':uuid,'pciBusId':g.attrib['id'],'product':g.findtext('product_name')},'dcgmVersion':'3.3.9','privateEngine':d['child'],'commands':[r for r in d['commands'] if r['argv'][:2]==['dcgmi','dmon'] or (r['argv'][:2]==['dcgmi','test'] and '--inject' in r['argv'])]}
nvml={'runId':RUN,'source':'operator-collected live nvidia-smi/NVML, not a model inference','beforeAt':xml[0]['at'],'afterAt':xml[1]['at'],'driverVersion':E.fromstring(xml[0]['stdout']).findtext('driver_version'),'allEightGpuEccAndRemapUnchanged':True,'targetGpuBefore':d['allEightGpuEccAndRemapBefore'][0],'targetGpuAfter':d['allEightGpuEccAndRemapAfter'][0],'currentComputeProcessesCommand':next(r for r in d['commands'] if r['argv'][0]=='nvidia-smi' and '--query-compute-apps=' in ' '.join(r['argv'])),'limitations':['Read-only sample comparison is not an active hardware diagnostic or RMA verdict.','These are timestamped snapshots, not continuous GPU sampling.']}
context=json.loads((ROOT/'gpu-context-v2.private.json').read_text());kernel=next(r for r in context['commands'] if r.get('argv',[None])[0]=='dmesg')
kernel={'runId':RUN,'source':'operator-collected live available kernel ring','capture':kernel,'matchingXidLines':[s for s in kernel['selectedLines'] if 'Xid' in s or 'NVRM' in s],'limitations':['Kernel ring may have rotated. No matching Xid in available records does not prove no historical error.','Original broad selector also matched a network interface name containing ecc; that line is not an ECC event.','This artifact is a collected snapshot; no NVDebug, BMC dump, stress test or production reset was performed.']}
base={'runId':RUN,'allEightGpuEccAndRemapBefore':d['allEightGpuEccAndRemapBefore'],'allEightGpuEccAndRemapAfter':d['allEightGpuEccAndRemapAfter']}
metric_labels={'run_id':RUN,'node':'target-node-1','gpu':'0','gpu_uuid':uuid,'simulation':'true','evidence_source':'isolated_dcgm_cache_snapshot'}
labels=','.join(k+'='+json.dumps(v) for k,v in metric_labels.items())
metrics=''
for name,value,desc in [('mosaic_test_dcgm_xid_error',95,'Replayed isolated DCGM cache Xid, not a live hardware event'),('mosaic_test_dcgm_ecc_dbe_volatile_total',1,'Replayed isolated DCGM cache volatile DBE'),('mosaic_test_dcgm_ecc_dbe_aggregate_total',1,'Replayed isolated DCGM cache aggregate DBE')]:
 metrics+='# HELP '+name+' '+desc+'\n# TYPE '+name+' gauge\n'+name+'{'+labels+'} '+str(value)+'\n'
(ROOT/'gpu-test-metrics.prom').write_text(metrics)
shared={'run_id':RUN,'mosaic_test':'true','experiment':'gpu-telemetry-cache'}
meta=lambda name,namespace=None:{'name':name,'labels':dict(shared),**({'namespace':namespace} if namespace else {})}
cm={'apiVersion':'v1','kind':'ConfigMap','metadata':meta('gpu-evidence',NS),'data':{name:json.dumps(value,ensure_ascii=False,indent=2)+'\n' for name,value in [('dcgm.json',dcgm),('nvml.json',nvml),('kernel.json',kernel),('all-gpu-baseline.json',base)]}}
cm['data']['metrics']=metrics
image=json.loads((ROOT.parent/'e2e-20261031t075722z/selected-fixture-image.json').read_text())['repoDigests'][0]
containers=[]
for name,key in [('telemetry','dcgm.json'),('nvml-witness','nvml.json'),('kernel-witness','kernel.json')]:
 command='cat /evidence/'+key+'; '+('exec httpd -f -p 8080 -h /evidence' if name=='telemetry' else 'exec sleep 86400')
 c={'name':name,'image':image,'imagePullPolicy':'Never','command':['sh','-c',command],'resources':{'requests':{'cpu':'5m','memory':'8Mi'},'limits':{'cpu':'50m','memory':'32Mi'}},'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},'volumeMounts':[{'name':'evidence','mountPath':'/evidence','readOnly':True}]}
 if name=='telemetry':c.update(ports=[{'name':'metrics','containerPort':8080}],readinessProbe={'httpGet':{'path':'/metrics','port':'metrics'},'periodSeconds':5})
 containers.append(c)
pod={'apiVersion':'v1','kind':'Pod','metadata':meta('gpu-telemetry-fixture',NS),'spec':{'automountServiceAccountToken':False,'restartPolicy':'Never','nodeSelector':{'kubernetes.io/hostname':'target-node-1'},'tolerations':[{'key':'node-role.kubernetes.io/control-plane','operator':'Exists','effect':'NoSchedule'}],'securityContext':{'runAsNonRoot':True,'runAsUser':65534,'runAsGroup':65534,'seccompProfile':{'type':'RuntimeDefault'}},'containers':containers,'volumes':[{'name':'evidence','configMap':{'name':'gpu-evidence','defaultMode':292}}]}}
service={'apiVersion':'v1','kind':'Service','metadata':meta('gpu-telemetry-fixture',NS),'spec':{'selector':shared,'ports':[{'name':'metrics','port':8080,'targetPort':'metrics'}]}}
monitor={'apiVersion':'monitoring.coreos.com/v1','kind':'ServiceMonitor','metadata':meta('gpu-telemetry-fixture',NS),'spec':{'selector':{'matchLabels':shared},'namespaceSelector':{'matchNames':[NS]},'endpoints':[{'port':'metrics','path':'/metrics','interval':'5s','scrapeTimeout':'3s'}]}}
monitor['metadata']['labels']['release']='kube-prometheus-stack'
rule={'apiVersion':'monitoring.coreos.com/v1','kind':'PrometheusRule','metadata':meta('mosaic-'+RUN,'monitoring'),'spec':{'groups':[{'name':'mosaic-'+RUN,'interval':'5s','rules':[{'alert':'MosaicGpuTelemetrySimulation','expr':'mosaic_test_dcgm_xid_error{run_id="'+RUN+'",simulation="true"} == 95','for':'45s','labels':{'severity':'info',**shared,'simulation':'true','test_namespace':NS,'test_pod':'gpu-telemetry-fixture'},'annotations':{'summary':'GPU telemetry test: isolated DCGM Xid 95 and ECC snapshot','description':'test from Jeff Peng. Run '+RUN+'. GPU telemetry simulation, not a CPU crash or a physical hardware fault. Cluster target-lab, namespace '+NS+', Pod gpu-telemetry-fixture. In View mode read logs from telemetry, nvml-witness, kernel-witness; compare isolated DCGM cache with unchanged live NVML and production DCGM. Then consult iraop_query collection mosaic-gpu-validation-20261031 for generic GPU triage procedure; keep incident facts separate from knowledge. Do not reset, drain or repair any GPU.','test_from':'test from Jeff Peng','evidence_source':'isolated_dcgm_cache_snapshot'}}]}]}}
rule['metadata']['labels']['release']='kube-prometheus-stack'
manifest={'apiVersion':'v1','kind':'List','items':[{'apiVersion':'v1','kind':'Namespace','metadata':meta(NS)},cm,pod,service,monitor,rule]}
(ROOT/'gpu-fixture.prepared.private.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'objects':[{'kind':x['kind'],'name':x['metadata']['name'],'namespace':x['metadata'].get('namespace')} for x in manifest['items']],'configmapKeyBytes':{k:len(v.encode()) for k,v in cm['data'].items()},'gpuResourceRequests':0,'podName':'gpu-telemetry-fixture'}))
