"""Lightweight audit of completed measurements; no heavy scoring or refitting."""
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import hashlib,json,statistics

ROOT=Path(__file__).resolve().parent

def rows(name):
    path=ROOT/"results"/name
    if not path.exists():return []
    result=[]
    contents=path.read_text();lines=contents.splitlines()
    for i,line in enumerate(lines):
        try:result.append(json.loads(line))
        except json.JSONDecodeError:
            if i==len(lines)-1 and not contents.endswith("\n"):continue
            raise # Only a currently appended final record can be incomplete.
    return result

def measured(row):return not row.get("warmup") and row.get("diag",0)==0 and row.get("fault",0)==0

def group(data,keys):
    grouped=defaultdict(list)
    for row in data:
        if measured(row):grouped[tuple(row.get(key) for key in keys)].append(row)
    result=[]
    for key,values in sorted(grouped.items(),key=lambda item:str(item[0])):
        entry=dict(zip(keys,key));entry["repetitions"]=len(values)
        for field in ("full_vm_seconds","wall_seconds","global_communication_mb","party0_rounds","max_rss_single_child_kib"):
            numbers=[float(row[field]) for row in values if row.get(field) is not None]
            if numbers:entry[field]={"mean":statistics.mean(numbers),"sd":statistics.stdev(numbers) if len(numbers)>1 else None,"min":min(numbers),"max":max(numbers)}
        entry["raw_logs"]=[row["raw_log"] for row in values]
        entry["circuit_hashes"]=sorted({row.get("source_sha256",row.get("circuit_sha256")) for row in values})
        result.append(entry)
    return result

def main():
    result={"generated_utc":datetime.now(timezone.utc).isoformat(),"status":{},"comparisons":{},"quality":{}}
    for name in ("aes_baseline","poly_query","vector_query","sface","projection_facenet","projection_sface","lazy_persistence","shared_query","virtual_scale","private_client","calibration_repair","frontend_confirmation","network"):
        path=ROOT/f"results/{name}_status.json"
        if path.exists():
            try:result["status"][name]=json.loads(path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:result["status"][name]={"temporarily_being_written":True}
    persisted=[]
    for filename,method in (("persisted_runs.jsonl","eager"),("lazy_persisted_runs.jsonl","virtual")):
        persisted.extend({**row,"method":method} for row in rows(filename) if row.get("tag")=="paired_virtual_persistence")
    result["comparisons"]["persisted_rekey"]=group(persisted,("n","mode","method"))
    result["comparisons"]["larger_real_gallery"]=group([r for r in rows("lazy_epoch_runs.jsonl") if r.get("tag")=="virtual_scale_comparison"],("n","mode","locator_representation"))
    result["comparisons"]["index_operator_vector"]=group([r for r in rows("vector_query_runs.jsonl") if r.get("tag") in ("vector_query_comparison","vector_query_scale")],("n","mode","circuit_name"))
    inputs=[]
    for filename,method in (("lazy_persisted_runs.jsonl","owner_input"),("shared_query_runs.jsonl","external_shared_client")):
        inputs.extend({**r,"method":method} for r in rows(filename) if r.get("tag")=="query_input_interface_comparison")
    result["comparisons"]["query_input_interface"]=group(inputs,("n","mode","method"))
    private=[]
    for filename,method in (("private_client_runs.jsonl","polynomial_or_fullscan"),("private_fused_runs.jsonl","fused")):
        private.extend({**r,"method":method} for r in rows(filename) if r.get("tag")=="private_output_query_comparison")
    result["comparisons"]["private_output_full_query"]=group(private,("n","mode","method"))
    network=rows("network_runs.jsonl")
    result["comparisons"]["network_delay"]=group(network,("n","root_bits","mode","requested_added_rtt_ms","locator_representation"))
    calibrations={}
    for row in network:
        if measured(row):calibrations[row["requested_added_rtt_ms"]]=row["echo_calibration"]
    result["network_audit"]={"calibrations":calibrations,"backpressure_events":sum(row["network_emulation"]["backpressure_events"] for row in network),"maximum_direction_queue_bytes":max([row["network_emulation"]["max_direction_queue_bytes"] for row in network] or [0]),"scope":"Task-local stream delay; all parties on one host, no packet-loss/bandwidth model. N2D64 rekey and N8D512 query, reported separately."}
    for frontend in ("facenet","sface"):
        corrected=ROOT/f"results/projection_{frontend}_corrected/summary.json"
        path=corrected if corrected.exists() else ROOT/f"results/projection_{frontend}/summary.json"
        if path.exists():
            summary=json.loads(path.read_text())
            result["quality"][frontend]={"n4096":[r for r in summary["closed_set"] if r["n_gallery"]==4096],"source_summary":str(path.relative_to(ROOT))}
    confirmation=ROOT/"results/frontend_confirmation/summary.json"
    if confirmation.exists():result["quality"]["paired_confirmation"]=json.loads(confirmation.read_text())
    result["open_set_precision_status"]="Use only *_corrected projection/binary_frontend outputs after calibration_repair passes; original float32-score open-set attempts have a strict-threshold rounding defect. Rank1/Rank5 and MPC timings are unaffected."
    path=ROOT/"results/current_results.json";path.write_text(json.dumps(result,indent=2))
    lines=["Текущий проверяемый результат revision_v3",result["generated_utc"],"", "Это сводка фактических измерений. Незавершённые серии не выдаются за итоговые.","Время: полная MPC VM; связь: global MB пяти сторон. Все стороны на одном хосте.",""]
    labels={"persisted_rekey":"Смена ключей из реально сохранённых долей", "larger_real_gallery":"Большие реальные галереи LFW, холодный ввод", "index_operator_vector":"Оператор индексных кандидатов (обязателен отдельный full-scan baseline)", "query_input_interface":"Внешний клиент: доли запроса вместо открытого ввода одной стороне", "private_output_full_query":"Полный запрос с ответом только клиенту"}
    lines.extend(["Open-set новые ITQ/projection: использовать только *_corrected после успешного calibration_repair. Float32 округлял строгий порог; исходные попытки сохранены. Rank1/Rank5 и MPC не затронуты.",""])
    for family,entries in result["comparisons"].items():
        lines.append(labels.get(family,"Изолированная эмуляция сетевой задержки; размеры не экстраполируются"))
        for row in entries:
            fields=[f"{key}={value}" for key,value in row.items() if key not in ("raw_logs","circuit_hashes") and not isinstance(value,dict)]
            for key,label in (("full_vm_seconds","сек"),("global_communication_mb","MB")):
                if key in row:
                    metric=row[key];fields.append(f"{label}={metric['mean']:.6f}, SD={metric['sd'] if metric['sd'] is not None else 'NA'}")
            lines.append("; ".join(fields))
        if not entries:lines.append("Нет завершённых производительных измерений.")
        lines.append("")
    lines.extend(["Качество, N4096 (все варианты сохранены)"])
    for frontend in ("facenet","sface"):
        for row in result["quality"].get(frontend,{}).get("n4096",[]):
            lines.append(f"{frontend} {row['method']}: Rank1={100*row['rank1']:.4f}%, Rank5={100*row['rank5']:.4f}%")
    lines.extend(["", "Границы интерпретации", "Виртуальные эпохи меняют представление: логические секретные handles стабильны; все доли обновляются. Это не физическое преобразование всех значений индекса.", "Полиномиальная выборка улучшает отдельный оператор; полный поиск уже вычисляет все Hamming-расстояния. Из этого ускорения нельзя выводить ускорение полной идентификации.", "SFace/RP512 меняет модель, выравнивание и кодирование вместе. Гиперплоскости известны и открыты; это не криптографическая новизна. Обновление frontend требует признаков/перерегистрации.", "Сравнение AES относится к данной реализации MPC. Обычное шифрование поддерживает тот же полезный контракт; универсального превосходства над AES нет.", "Корректность/абляции при пассивной MPC не являются malicious-security доказательством. DIAG1 содержит доверенные оракулы и не доказывает приватность производительного интерфейса.", "Сетевая серия завершена при наличии network.finished=true. Это task-local emulation; all-party localhost, разные N/d/операции не объединяются. Актуальная готовность PDF и архива: results/final_evidence_audit.json и output/package_manifest.json, если созданы и соответствуют файлам.", "", "Состояние очереди"])
    for name,status in result["status"].items():lines.append(f"{name}: finished={status.get('finished')}, correctness={status.get('correctness_passed')}, current={status.get('current')}, error={status.get('last_error')}")
    lines.extend(["", "Все строки, разброс, исходные логи и SHA схем доступны в results/current_results.json.","Контрольный пакет revision_v2 сохранён. Финальный архив revision_v3 и его проверка фиксируются отдельно в output/package_manifest.json; новые сводки его автоматически не публикуют."])
    (ROOT/"CURRENT_RESULTS_RU.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"comparisons":{name:[{key:value for key,value in row.items() if key not in ("raw_logs","circuit_hashes")} for row in entries] for name,entries in result["comparisons"].items()}},indent=2))

if __name__=="__main__":main()
