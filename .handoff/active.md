# Handoff · navindex · 2026-08-11

## Goal
Suporte a C# e filtro de `.gitignore` no `navindex.py` — entregue e no `origin/main`. O que sobra
é rodagem em outros repos e as arestas conhecidas listadas em Open.

## State
- HEAD: `4ad0dfc` (`feat: index C# and skip gitignored paths`), pushado. Working tree limpo.
- Live state: nada rodando. O consumidor real da mudança é o repo `Codyte/Tia-Portal-CLI`
  (`~/.agents/skills/tia`, HEAD `f2adeba`), que já apagou o gerador paralelo `scripts/navi-cs.ps1`
  e depende deste comportamento — regressão aqui quebra a navegação de lá.
- Done:
  - **C# (`.cs`)**: `CODE_EXT`, `comment_token` (`//`), `docstring_end` (ramo JS, header entra
    abaixo de banner `/* */`), ramo novo em `symbols()` com `CS_TYPE`/`CS_METHOD`/`CS_PROP`/
    `CS_CASE`, `CS_KW`, e o hook pre-commit agora pega `.cs`.
  - **`git_ignored()` + filtro no `walk()`**: 1 subprocess por rodada, `--include-ignored` desliga.
  - `CACHE_VER` 4 → 5. Testes novos (símbolos C#, header idempotente com BOM/EOL, walk com
    `.gitignore` em repo temporário). SKILL.md, README.md e `references/internals.md` atualizados.
  - Validação real: 17 `.cs` do repo tia headerizados, `pwsh scripts/rebuild.ps1` **ALL PASS**,
    3ª rodada não muda byte nenhum (idempotência conferida por `md5sum -c`).
- In progress: nada.

## Decisions (and why)
- **Linha de membro em C# exige ≥1 modificador** e o slot de tipo de retorno recusa `=`. É o que
  mantém `if (`/`foreach (` fora do índice e faz `static readonly Regex Rx = new Regex(...)`
  continuar sendo campo, não um método chamado `Regex`.
- **O indent de membro pula a chave solta sob o tipo.** Em C# o `{` de `class X` fica no indent do
  *tipo*; adotá-lo como indent de membro achava zero membros.
- **Tipo aninhado é indexado mas não reseta o indent de membro** — resetar fazia sumir todo membro
  do tipo externo declarado depois dele.
- **`case "literal":` entra em qualquer profundidade**, sem gate de indent: numa CLI a tabela de
  verbos é o alvo real de busca (71 verbos no `Program.cs` do tia). Case numérico/enum fica fora.
- **`git ls-files --others --ignored --exclude-standard --directory`, não `git check-ignore`** —
  uma chamada por rodada em vez de milhares de processos. `--others` por construção nunca lista
  arquivo rastreado, então arquivo versionado que casa com regra de ignore continua indexado.
- **`core.quotePath=false` é obrigatório** — sem ele pasta com acento volta octal-escapada
  (`\303\247`) e o prefixo nunca casa. Foi encontrado testando contra pasta em PT-BR.
- **Descartado: pôr `proj`/`workspace` em `SKIP_DIRS`.** Nomes genéricos demais para banir numa
  ferramenta global; a regra certa é o `.gitignore` do repo.
- **Descartado: subir o teto de 24 símbolos do preview** de `write_map`. O header no topo do
  arquivo já carrega a lista inteira, que é o desenho de 2 leituras da skill.

## Next steps (ordered)
1. Rodar em outro repo C# real (um com `record`, `partial class` e namespace file-scoped) e ver
   se o indent de membro se segura — só o layout `namespace { class { … } }` foi exercitado.
2. `evals/evals.json` não ganhou caso de C# nem de `.gitignore`; o `test_navindex.py` cobre os dois.
3. Se aparecer repo grande e sujo, medir o custo do `git ls-files` (hoje assumido desprezível).

## Key files
- `scripts/navindex.py` — header NAV INDEX no topo tem a linha de cada símbolo; `git_ignored`,
  `walk`, `symbols` são os pontos tocados.
- `scripts/test_navindex.py` — amostra `CS` + o teste de `.gitignore` em `tempfile` com `git init`.
- `references/internals.md` — regras por linguagem (seção **C#**) e a seção **Gitignored paths**.
- `__navi__.md` / `scripts/__navi__.md` — mapas do próprio repo, regenerados.

## Open / blockers
- **Assinatura em várias linhas continua fora** (teto declarado com comentário `ponytail:`), igual
  aos ramos JS e Python.
- **Campo simples de C# não é indexado** de propósito (só método, construtor e propriedade). Se
  algum repo depender de constante pública, é regra nova, não bug.
- **`--include-ignored` não tem teste dedicado** — o caminho contrário (sem filtro) é o testado.
- Repos que já tinham mapas cobrindo pasta gitignored vão **encolher** na primeira regeneração
  depois deste release. É o objetivo, mas surpreende quem não leu o CHANGELOG (no tia a árvore
  caiu de 263 arquivos/44 pastas para 84/10).

## Skills
- navindex

## Effort
**Baixo** para o passo 1 — é rodar o script num repo e ler o mapa; a régua já existe
(`test_navindex.py` + `internals.md`). Sobe para **médio** se o layout novo (namespace
file-scoped, `record` de uma linha) exigir mexer no indent de membro, que é a parte frágil da
extração. Raciocínio não é o gargalo: o custo é achar um repo C# com layout diferente.
