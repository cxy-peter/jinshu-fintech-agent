"""Run fixed synthetic tasks through the real adapted Harness. Not an LLM accuracy study."""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jinshu.runtime import Runtime
from jinshu.fixtures import WORKFLOWS


async def evaluate(output: Path) -> dict:
    runtime = await Runtime().initialize()
    results = []
    try:
        for index, (key, workflow) in enumerate(WORKFLOWS.items()):
            questions = [workflow['name'] + '请给出处理依据',
                         workflow['name'] + '有哪些需要人工复核']
            for sample, question in enumerate(questions):
                response = await runtime.ask(question,
                    user_id=f'holdout_{index}_{sample}', workflow=key)
                trace = await runtime.c.store.get('traces', response['trace_id'])
                trace['eval_split'] = 'frozen_holdout'
                await runtime.c.store.upsert('traces', trace)
                results.append({'workflow': key, 'query': question,
                    'source_integrity_pass': response['verification']['passed'],
                    'trace_id': response['trace_id'],
                    'tool_names': [x['tool'] for x in response['tool_results']],
                    'semantic_accuracy_claimed': False})
        documents = await runtime.c.store.list_documents()
        chunks = await runtime.c.store.list_all_chunks()
        report = {'documents': len(documents), 'chunks': len(chunks),
            'table_chunks': sum(bool(c['metadata'].get('has_table')) for c in chunks),
            'workflows': len(WORKFLOWS), 'tasks': len(results),
            'source_integrity_passed': sum(r['source_integrity_pass'] for r in results),
            'scope': 'Synthetic deterministic task/source regression, not learned model QA accuracy',
            'results': results}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return report
    finally:
        await runtime.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'evidence/task_regression_latest.json')
    args = parser.parse_args()
    report = asyncio.run(evaluate(args.out))
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report['source_integrity_passed'] == report['tasks'] else 1)
