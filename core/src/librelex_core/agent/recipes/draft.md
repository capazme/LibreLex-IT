<!-- Derived from mcp-legal-it plugin/skills/genera-atto/SKILL.md and plugin/agents/redattore-atti.md
     (worktree json-output-and-entrypoint, 2026-09-19). Adapted to Writer: the act goes into the
     document one partition per insertion; calculations, verified references, attachments checklist
     and warnings are reported in the panel. Keep the rules in sync with the plugin. -->
# Ricetta di redazione (stessa procedura della skill genera-atto)

## Regole fondamentali
1. CATALOGO: il modello d'atto ti è già stato fornito nei dati di questo messaggio (struttura, campi, strumenti di calcolo, riferimenti normativi, avvertenze): non ridefinirlo, seguilo.
2. ANCORAGGIO: prima di citare qualsiasi norma nel testo dell'atto chiama `cite_law` sul riferimento; le sentenze solo dopo averle lette con uno strumento `leggi_*`.
3. CALCOLI: gli importi (contributo unificato, interessi, rivalutazione, compensi, scadenze) si calcolano sempre con gli strumenti indicati in `tool_calcolo`, mai a mano; riporta nell'atto i risultati e la data del calcolo.
4. COMPLETEZZA: non generare l'atto finché mancano campi obbligatori; chiedili con `chiedi_dati`.
5. FORMULE LEGALI: usa le formule esatte dei generatori e dei modelli, non parafrasarle; se una base deterministica è già nel documento non riscriverla.
6. RISERVATEZZA: se è disponibile un atto di riferimento (caso simile), leggilo con `leggi_atto_riferimento` e prendine struttura, titoli, stile, formule e argomentazioni; non riusare mai i suoi fatti, nomi, importi, date o estremi di causa, e verifica con `cite_law` ogni norma che ne ricavi.

## Procedura
1. Dati: hai già il modello d'atto, i campi compilati dall'utente, le note e, se presente, la base inserita con i suoi segnaposto. Leggi il documento con `read_paragraphs` solo se devi vedere testo già presente (partizioni inserite in un turno precedente, dati scritti dall'avvocato).
2. Domande: se manca un campo obbligatorio o un dato necessario ai calcoli o alle premesse in fatto, chiama `chiedi_dati` una sola volta con tutte le domande (al massimo otto, ciascuna con `campo`, `domanda`, `esempio` e `tipo`), poi fermati: le risposte arrivano nel turno successivo. Non chiedere ciò che i campi, le note o l'atto di riferimento già dicono.
3. Calcoli: chiama ogni strumento di `tool_calcolo` con i dati raccolti.
4. Base: se il documento contiene già la base deterministica, riempi i segnaposto con `replace_text` (uno per chiamata, testo esatto tra parentesi quadre) e poi inserisci le partizioni narrative che mancano con `insert_markdown` (`where="end"`, oppure `after:<id>` per collocarle dopo un paragrafo della base). Se non c'è una base, componi l'atto seguendo la struttura del modello, una partizione per chiamata: intestazione e parti; premesse in fatto; motivi in diritto; conclusioni con le somme calcolate; documenti allegati.
5. Norme: ogni norma nel testo passa da `cite_law` prima di essere citata; la verifica automatica all'inserimento segnala con un commento ciò che non risulta.
6. Chiusura: quando l'atto è completo chiama `redazione_completata` con un riepilogo in testo semplice (senza markdown) in quattro parti: tabella dei calcoli eseguiti (strumento, dati, risultato), riferimenti normativi verificati, elenco degli allegati necessari, avvertenze del modello e ciò che resta da completare a mano. Poi rispondi in chat con due righe.

## Stile
Registro forense, formule complete, nessun asterisco o markdown nelle risposte in chat; nel documento usa titoli per le partizioni ed elenchi numerati per motivi e allegati; lascia tra parentesi quadre ciò che nessuno ti ha fornito.
