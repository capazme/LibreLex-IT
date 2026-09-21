# Punto di design: pannello Redazione (2026-09-20)

Questo documento chiude il punto di design chiesto dall'avvocato prima del Task 5. Mette insieme quattro ricerche sul web (API Sidebar, palette dei controlli AWT, copiloti legali per Word, precedenti Python-UNO), due proposte di design scritte con lenti diverse, e i fatti verificati nel worktree (tabella `layout.py`, `panel.py`, `document.py`, `protocol.py`, il probe headless `scratchpad/probe.out` su LibreOffice 26.8).

Verdetto in una riga: il design a quattro passi è giusto e va tenuto; quello che manca è orientamento (in che passo sono), leggibilità (colori fissi, sezioni), consenso impossibile da mancare, tastiera. Tutto questo entra nel Task 5 senza cambiare l'architettura né le tabelle già testate. L'altezza dinamica, i campi tipizzati, il Roadmap e gli hyperlink aspettano una misura e uno spike.

Convenzioni: du = dialog units (AppFont). "Spike Sn" rimanda alla sezione 7. Le fonti in forma breve rimandano alla sezione 8.

## 1. Cosa permette LibreOffice

### 1.1 Il pannello e il deck

- **Altezza negoziata, non fissa.** `XSidebarPanel.getHeightForWidth(width)` ritorna una `LayoutSize` (Minimum, Maximum, Preferred; `-1` vale "nessun limite"). Il layouter del deck la chiede a ogni pannello. Non esiste nell'API alcun tetto tipo "404 unità": è una scelta nostra. Fonte: [XSidebarPanel](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XSidebarPanel.html); [Sidebar for Developers](https://wiki.openoffice.org/wiki/Sidebar_for_Developers).
- **Ridimensionare a runtime.** Un pannello che vuole cambiare altezza (contenuto diverso dopo un cambio di contesto) chiama `XSidebar.requestLayout()`; il layouter richiama `getHeightForWidth`. Fonte: [XSidebar](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XSidebar.html).
- **Larghezza.** `getMinimalWidth()` in pixel; se è sotto il massimo configurato, minima + 100 px diventa il nuovo massimo della sidebar. Fonte: [XSidebarPanel](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XSidebarPanel.html).
- **Titolo del pannello a runtime.** `XPanel.setTitle()`, oltre a `collapse()`, `expand()`, `getOrderIndex/setOrderIndex`, `moveUp/moveDown`. Fonte: [XPanel](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XPanel.html). Il percorso dal pannello al proprio `XPanel` (via `frame.getController().getSidebar().getDecks()`) è confermato dal design §1 per `collapse()` e resta l'assunzione 1 del design §8: spike S2.
- **Deck da codice.** `XDeck.activate(True)`, `getPanels()`, `setTitle()`. Fonte: [XDeck](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XDeck.html). `XSidebarProvider.setVisible/getDecks/getSidebar/showDecks`. Fonte: [XSidebarProvider](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XSidebarProvider.html). Tutte disponibili dalla 5.1, quindi garantite sul target 26.2+.
- **Configurazione.** `Sidebar.xcu`: `DeckList` (Title, Id, IconURL), `PanelList` con `ContextList` "app, contesto, visible|hidden" (hidden = collassato alla sola barra del titolo) e `OrderIndex` per l'ordine verticale. Fonte: [Sidebar for Developers](https://wiki.openoffice.org/wiki/Sidebar_for_Developers); [lo-p Addons](https://flywire.github.io/lo-p/46-Addons.html).
- **Floating gratis.** La sidebar si stacca e si riaggancia; è comportamento del framework, non del pannello. Fonte: [help: docking](https://help.libreoffice.org/Common/Showing,_Docking_and_Hiding_Windows).
- **Linea guida TDF.** Il contenuto di un pannello deve stare nell'altezza del deck: lo scroll verticale è un antipattern. Fonte: [Design/Guidelines/SideBar](https://wiki.documentfoundation.org/Design/Guidelines/SideBar).

### 1.2 I controlli disponibili a un'estensione Python

- **Il pattern è quello standard.** `createInstance("com.sun.star.awt.UnoControl<Kind>Model")`, `insertByName` sul modello del container, `getControl(name)` per la vista. È il pattern del DevGuide, non un ripiego. Fonte: [Creating Dialogs at Runtime](https://wiki.openoffice.org/wiki/Documentation/DevGuide/Basic/Creating_Dialogs_at_Runtime); [XControlContainer](https://www.openoffice.org/api/docs/common/ref/com/sun/star/awt/XControlContainer.html).
- **Palette.** Oltre a FixedText, Edit, Button, ListBox, ProgressBar (già usati): `FixedLine` (separatore con etichetta), `GroupBox`, `CheckBox`, `RadioButton`, `DateField`, `NumericField`, `CurrencyField`, `FormattedField`, `ComboBox`, `FixedHyperlink`, `ImageControl`, `FileControl`. Tre compositi: `UnoControlRoadmapModel` (indicatore di passi dei wizard: item con ID, Label, Enabled, Interactive; `CurrentItemID` e `Complete` sul modello), `awt.grid.UnoControlGridModel` (tabella con ColumnModel e DataModel), `awt.tab.UnoControlTabPageContainerModel` (tab), `awt.tree.TreeControlModel`. Fonti: [Roadmap](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlRoadmapModel.html), [DevGuide Roadmap](https://wiki.openoffice.org/wiki/Documentation/DevGuide/GUI/Roadmap_Control), [Grid](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1grid_1_1UnoControlGridModel.html), [Grid wiki](https://wiki.openoffice.org/wiki/API/UNO_AWT/Grid_Control), [TabPageContainer](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1tab_1_1UnoControlTabPageContainer.html), [Tree](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1tree_1_1TreeControlModel.html), [FixedLine](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlFixedLineModel.html), [FixedHyperlink](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlFixedHyperlinkModel.html), [DateField](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlDateFieldModel.html), [CheckBox](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlCheckBoxModel.html).
- **Probe locale (spike già fatto).** `scratchpad/probe.out` su LibreOffice 26.8 headless: tutti i modelli sopra si istanziano e si inseriscono con `insertByName` in un `UnoControlDialogModel`; gli item del Roadmap si creano e si inseriscono; i modelli espongono `TabIndex`, `Tabstop`, `EnableVisible`, `TextColor`, `BackgroundColor`; Button espone `DefaultButton` e `ImageURL`. Il peer non si crea in headless ("Invalid xParent"): la resa a schermo dentro la sidebar resta da vedere a occhio (spike S3, S7, S8).
- **Testo.** `FixedText` ha `MultiLine` e `VerticalAlign` ma nessun auto-sizing: l'altezza si calcola a mano, come fa già `panel.py`. Fonte: [FixedTextModel](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlFixedTextModel.html). `Edit` ha `MultiLine`, `ReadOnly`, `VScroll`, `MaxTextLen`. Fonte: [EditModel](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlEditModel.html).
- **Unità.** Modelli in AppFont, viste in pixel; conversione con `XUnitConversion.convertSizeToPixel/convertSizeToLogic` e `MeasureUnit.APPFONT`. Fonti: [forum AppFont](https://forum.openoffice.org/en/forum/viewtopic.php?t=19891), [UnitConversion.java](https://github.com/LibreOffice/core/blob/master/toolkit/qa/complex/toolkit/UnitConversion.java).
- **Eventi.** `XActionListener` (Button, ListBox, ComboBox, FixedHyperlink), `XItemListener` (CheckBox, RadioButton, ListBox), `XTextListener`, `XFocusListener`; in Python con classi che ereditano `unohelper.Base` e l'interfaccia. Fonti: [XActionListener](https://www.openoffice.org/api/docs/common/ref/com/sun/star/awt/XActionListener.html), [ListenerProcAdapters.py](https://wiki.openoffice.org/wiki/Danny.OOo.Listeners.ListenerProcAdapters.py).
- **Immagini.** Le immagini nel pacchetto `.oxt` si raggiungono con `vnd.sun.star.extension://<id>/<path>`. Fonte: [Toolbar customization](https://github.com/eellak/gsoc2018-librecust/wiki/Toolbar-customization). L'SVG per `ImageURL` dei controlli AWT non è confermato: prudente assumere PNG. Fonte: [ButtonModel](https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlButtonModel.html).
- **Python puro è un pattern maturo.** Grammalecte e Lightproof sono in Python. Fonte: [Grammalecte](https://templates-arm.libreoffice.org/en/extensions/show/grammalecte). LibreThinker (sidebar, XSidebarPanel, circa 15k installazioni) è Python. Fonte: [librethinker-extension](https://github.com/mihailthebuilder/librethinker-extension). Il boilerplate più citato è però Java. Fonte: [allotropia sidebar extension](https://github.com/allotropia/libreoffice-sidebar-extension).

### 1.3 Cosa non permette (o non è documentato)

- **Niente widget nativi da Python.** `weld` e i file `.ui` GtkBuilder sono C++ interno; l'estensione ha solo i controlli AWT sulla finestra container. Fonte: [LibOCon 2020 slides](https://www.libreoffice.org/assets/libocon2020/Slides/LibreOfficeCon-2020-NativeGtkWidgets.pdf).
- **Nessun controllo HTML o browser** trovato per un `.oxt` Python: assenza di prova, non prova di assenza. Fonte: [docs.libreoffice.org/extensions](https://docs.libreoffice.org/extensions.html).
- **Disegno libero.** `XPaintListener` esiste, ma nessun esempio Python di pittura su un peer; `WantsCanvas` è sperimentale. Fonti: [XPaintListener](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1awt_1_1XPaintListener.html), [Sidebar for Developers](https://wiki.openoffice.org/wiki/Sidebar_for_Developers).
- **Dark mode su macOS.** Esiste un meta bug aperto sui problemi di dark mode (118017); nessuna fonte descrive come si comportano i controlli AWT in un pannello sidebar. Fonti: [Bug 118017 meta](https://www.mail-archive.com/libreoffice-bugs@lists.freedesktop.org/msg1010058.html), [Bug 160332](https://www.mail-archive.com/libreoffice-bugs@lists.freedesktop.org/msg1014856.html). Il testo sfocato su Retina è risolto dalla 7.1.2. Fonte: [Bug 138122](https://bugs.documentfoundation.org/show_bug.cgi?id=138122).
- **Accessibilità.** VoiceOver funziona "in generale", con eccezioni non specificate. Fonte: [help accessibility](https://help.libreoffice.org/latest/en-US/text/shared/guide/accessibility.html).
- **Comando `.uno` per un deck custom.** Non confermato; da codice si usa `XDeck.activate`. Fonte: [ux-advise 2024](https://lists.freedesktop.org/archives/libreoffice-ux-advise/2024-May/045906.html).
- **Nascondere la barra del titolo del pannello.** Non documentato da nessuna parte (domanda aperta della ricerca 1). L'unica via nota alla piena altezza è un deck con un solo pannello.
- **Progresso con totale.** Non è un limite di LibreOffice ma del protocollo: l'evento `status` del core porta solo `request_id` e `text` (`core/src/librelex_core/protocol.py`, classe `Status`). Un totale esiste solo per la verifica citazioni (`progress` con `done/total`).

## 2. Cosa fanno gli strumenti simili

| Pattern | Chi | Trasferibile come |
|---|---|---|
| Pannello dedicato che genera su richiesta, separato dal documento, con "tieni" o "rigenera" | Copilot in Word, [Draft with Copilot](https://support.microsoft.com/en-us/copilot-word) | Conferma la scelta: procedura guidata in un pannello, non chat inline |
| Modalità nominate nello stesso pannello stretto | Harvey Ask/Edit, [blog](https://www.harvey.ai/blog/improved-word-experience); Robin AI Ask/Draft/Edit/Research, [pagina](https://robinai.com/news-and-resources/robin-university/word-add-in-an-intelligent-ai-sidekick-for-contract-review) | Il passo corrente sempre nominato: riga di stato e titolo del pannello |
| Revisione prima di applicare, revisioni native dell'editor, interruttore auto/approva | CoCounsel Drafting, [help TR](https://www.thomsonreuters.com/en-us/help/cocounsel/legal/cocounsel-for-microsoft-word/about-transactional-drafting); Spellbook, [pagina](https://spellbook.com/learn/word-add-ins-for-enhanced-legal-drafting) | Già fatto: `insert_markdown` e `replace_text` scrivono con `RecordChanges` acceso e identità "LibreLex" (`document.py` righe 555 e 647). Il consenso esplicito resta l'altro pilastro (L. 132/2025, [ecnews](https://www.ecnews.it/legale/mondo-professione/ai-digitalizzazione/intelligenza-artificiale-responsabilita-aggravata-nella-redazione-degli-atti-giudiziari/)) |
| Precedenti e fonti caricati come contesto | Harvey, [drafting tools](https://www.harvey.ai/blog/harveys-new-drafting-tools-meet-you-where-you-work); Lexis Create+ Get Cited Docs, [pagina](https://legal.lexisnexis.com/AI-Powered-Drafting) | Gli allegati numerati del passo 1; più avanti "Allega norme citate" nel passo 4 |
| Riepilogo strutturato delle modifiche, con posizione e livello di rischio | CoCounsel, [blog TR](https://legal.thomsonreuters.com/blog/legal-drafting-meets-generative-ai/) | Il riepilogo del passo 4 a sezioni fisse |
| Una fase di "coaching" separata dopo la generazione | Copilot, [Coaching](https://techcommunity.microsoft.com/blog/microsoft365insiderblog/improve-your-content-using-coaching-with-copilot-in-word-for-the-web/4265714) | Verifica citazioni come passo di controllo, non come bottone tra gli altri |
| Libreria di clausole filtrabile e confronto affiancato | Henchman, [demo LawNext](https://www.lawnext.com/2024/07/how-it-works-a-demo-of-henchman-generative-ai-driven-contract-drafting-and-negotiation-within-word.html) | Dopo: formule di rito e modelli dello studio |
| Playbook di regole applicate in redazione | Legora, [workflows](https://legora.com/product/workflows), [Word Actions](https://legora.com/blog/introducing-legora-word-actions) | Dopo: regole di stile dello studio nella ricetta |
| Sidebar AI in Writer con controlli AWT base | LibreThinker, [repo](https://github.com/mihailthebuilder/librethinker-extension), [extensions.libreoffice.org](https://extensions.libreoffice.org/en/extensions/show/99471); WriterAgent, [repo](https://github.com/KeithCu/writeragent); AI Assistant, [pagina](https://extensions.libreoffice.org/en/extensions/show/41988); Collabora Online 26.04, [release](https://www.collaboraonline.com/blog/cool-26-04-release/) | Nessuno documenta layout oltre lo standard: il nostro `layout.py` è tra i pochi riferimenti Python praticabili |

Buchi: nessuna fonte descrive come questi prodotti gestiscono la larghezza ridotta del pannello (accordion, tab o chat); "Daisy" non è stato trovato; Simpliciter e LegaleAI sono candidati italiani non ancora studiati ([Simpliciter](https://simpliciter.ai/)).

## 3. Valutazione del design attuale

### 3.1 Cosa fa già bene

- **Un pannello, un passo alla volta, senza scroll.** È la linea guida TDF ([SideBar guidelines](https://wiki.documentfoundation.org/Design/Guidelines/SideBar)).
- **Controlli pre-creati e commutati per visibilità.** È il pattern del DevGuide ([Creating Dialogs at Runtime](https://wiki.openoffice.org/wiki/Documentation/DevGuide/Basic/Creating_Dialogs_at_Runtime)); la tabella è pura e testata senza UNO; un pannello ricostruito dal deck è identico al primo.
- **Consenso nello stesso pannello, tre scelte, nessuna scelta di default.** È il modello "review before apply" di CoCounsel e il vincolo della L. 132/2025.
- **Inserzioni come revisioni firmate LibreLex.** Verificato in `document.py`; è ciò che fanno CoCounsel e Spellbook.
- **Log in un Edit di sola lettura, tenuto nella sessione (200 righe) e ripetuto alla ricostruzione.** `session.py` `MAX_LOG_LINES = 200`.
- **ListBox per tutto ciò che si clicca** (catalogo, allegati, partizioni), su un solo `XItemListener`.
- **Collapse di Azioni e Citazioni all'avvio** via `XPanel.collapse()`, best effort ([XPanel](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XPanel.html)).
- **Floating e larghezza** ereditati dal framework: la tabella si riadatta già alla larghezza.

### 3.2 Cosa la ricerca e il codice mostrano debole

- **Nessun indicatore di passo.** La riga di stato dice cosa fare, non dove si è; il titolo "Redazione" non cambia mai, sebbene `XPanel.setTitle` esista.
- **Altezza fissa uguale per ogni passo.** Dalla tabella (calcolato con `layout.build("Drafting", 190)`): totale 436 du; i passi finiscono a 370 (1), 320 (2), 322 (3), 300 (4); il blocco consenso occupa 338..408; lo stato 412..432. L'API negozia l'altezza per pannello, quindi il passo 4 spreca circa 100 du che Risposte potrebbe usare.
- **Nessun numero du/px.** Il 404 non è mai stato misurato sul Mac dell'avvocato: se la sidebar è più bassa di 436 du, non solo il consenso ma anche la riga di stato finiscono sotto il bordo (spike S1).
- **Colori fissi.** `TextColor = 0x666666` su `TemplateNotes`, `QuestionsHint`, `DraftConsentText` (e in Azioni `Notice`, `ConsentText`; in Citazioni `CitationsHint`). È l'unico rischio concreto di dark mode nella tabella: grigio su scuro (meta bug 118017).
- **Sezioni come FixedText in grassetto.** Il separatore nativo dei dialoghi è `FixedLine`, che il probe istanzia.
- **Tastiera.** Nessun `TabIndex` esplicito, nessun focus al cambio di passo, `Notes` multilinea in mezzo al flusso.
- **Due liste di partizioni con comportamenti diversi.** `Expected` (passo 3) non ha l'item listener; solo `Partitions` è nella tupla di `_build_controls` (`panel.py`).
- **Continua fissato sotto otto righe pre-allocate.** Con tre domande resta un buco di circa 170 du sopra il bottone.
- **Difetto di codice da correggere nel Task 5.** `panel.py` righe 97 e 98: `_default_label("Questions", ...)` legge `layout.CONTROLS["Questions"]`, che non esiste più (`KINDS` ha quattro voci): `KeyError` all'import, verificato con un import della tabella; `set_questions` scrive `QuestionsStatus`, controllo assente. Il piano prevede già la rimozione del ramo `Questions` nel Task 5.
- **Feedback nel passo 3.** Gli eventi `status` portano solo testo (`protocol.py`): una barra con totale non è onesta; un log riga per riga sì, e c'è.

## 4. Raccomandazioni

Ordinate per valore per l'avvocato. "Adesso" significa dentro il Task 5, nel contratto del piano: area 404 du più riga di stato, totale 436, tabelle e test del Task 3 immutati salvo dove detto.

| # | Cambiamento | API | Ispirazione | Sforzo | Rischio | Quando | Perché |
|---|---|---|---|---|---|---|---|
| 1 | Prefisso di passo nella riga di stato: "Passo 2 di 4 · Rispondi alle 3 domande e premi Continua" | `render_draft_status` (pura, già a passi) + `UnoControlFixedTextModel.Label` | Harvey Ask/Edit, Robin AI modes | piccolo | basso | adesso, Task 5 | Zero altezza, zero controlli nuovi: il primo rimedio al "dove sono" |
| 2 | Titolo del pannello al cambio passo: "Redazione · 2/4 Domande", best effort, riapplicato in `_replay` | `XSidebarProvider.getDecks()` → `XDeck.getPanels()` → `XPanel.setTitle()`, in `suppress(Exception)`; `XSidebar.requestLayout()` solo se non si ridisegna | Copilot Draft pane; wizard | piccolo | basso | adesso, Task 5 | Stesso percorso di `_collapse_other_panels()`; spike S2 nel field test |
| 3 | Via ogni `TextColor` fisso da tutti i pannelli; nessun `BackgroundColor`; l'enfasi resta al grassetto | `UnoControlFixedTextModel` senza `TextColor` | meta bug 118017 | piccolo | basso | adesso, Task 5 | Unico rischio dark mode nella tabella; costo nullo |
| 4 | Consenso "modale": mentre pende, `Continue` nascosto e `DraftCancel` disabilitato, riga di stato "In attesa del tuo consenso: Doc. 1, Doc. 2 (24.100 caratteri)", focus sul blocco, nessun `DefaultButton` | `XWindow.setVisible/setFocus`, `Enabled` | CoCounsel review before apply; L. 132/2025 | piccolo | basso | adesso, Task 5 | Il consenso non si può né mancare né dare per sbaglio; lo slot in basso resta (test del Task 3) |
| 5 | `FixedLine` al posto delle sezioni in grassetto (`FieldsLabel`, `NotesLabel`, `AttachmentsLabel`, `ExpectedLabel`, `PartitionsLabel`), stessi nomi, stessa altezza 10 du | `UnoControlFixedLineModel` (Label, Orientation) | dialoghi nativi di LibreOffice | piccolo | basso | adesso, Task 5 (solo il `kind` nella tabella) | Separatore nativo disegnato dal tema; geometria invariata, i test cambiano solo il kind; ripiego: `FixedText` se S3 fallisce |
| 6 | Ordine di tabulazione e focus di ingresso: `TabIndex` progressivo in ordine di tabella in `_build_controls`, `setFocus` sul primo controllo utile a ogni `set_step` (TemplateSearch, Answer1, DraftCancel, ResumeInput); nessun `DefaultButton` | `TabIndex`, `Tabstop`, `XWindow.setFocus` | dialoghi LibreOffice | piccolo | basso | adesso, Task 5 | La tastiera segue la lettura; Invio non avvia nulla per sbaglio; spike S5 |
| 7 | Liste partizioni unificate: `Expected` e `Partitions` con lo stesso render (✓ sulle inserite) e lo stesso click-to-jump; selezione azzerata dopo il salto | `StringItemList`, `SelectedItems` sotto `_quiet_items`, "Expected" aggiunto alla tupla degli item listener | Navigator di Writer; CoCounsel change list | piccolo | basso | adesso, Task 5 | Il passo 4 è la lista che l'avvocato ha visto riempirsi; un secondo clic sulla stessa riga rifunziona; spike S11 |
| 8 | `Continue` subito sotto l'ultima riga di domanda visibile (y = 28 + n·34 + 4) | `UnoControlModel.PositionY` a runtime, come già in `windowResized` | Copilot Draft pane | piccolo | basso | adesso, Task 5 | Niente buco con tre domande; l'invariante dei test (posizione massima) resta |
| 9 | Misura nel field test: du → px e altezza disponibile del deck, scritte nel log | `XUnitConversion.convertSizeToPixel(Size(0, 436), APPFONT)`, `getPosSize().Height` | linea guida TDF | piccolo | basso | adesso, Task 5 | Senza numeri l'altezza dinamica si decide a naso; spike S1 |
| 10 | Gate di accettazione: uno screenshot per passo in chiaro e in scuro su macOS | procedura del field test | meta bug 118017 | piccolo | basso | adesso, Task 5 | Nessuna fonte sui controlli AWT in dark mode: si guarda; spike S4 |
| 11 | Righe di log con ora e marcatore: "14:33 ✓ Inserito: Premesse in fatto", "14:34 ? Chiedo 3 dati", "✗ Errore: …" | `render.py` (pura) + `session.py` | Copilot Draft; CoCounsel | piccolo | basso | v0.8 | Tocca il Task 4 chiuso e le attese del Task 6 (righe che iniziano con "Inserito: "): si fa con i suoi test, dopo |
| 12 | Etichette allegati con tipo e stato: "Doc. 2 · fattura_12.pdf · PDF · 12.300 caratteri, troncato" | `render_attachments` | Harvey precedents; Lexis cited docs | piccolo | basso | v0.8 | La sessione ha già `kind` e `troncato`; cambia una stringa attesa dall'e2e |
| 13 | Altezza per passo: `Preferred` diverso per passo (398, 436, 436, 328 du) e `requestLayout()` in `set_step`; `DraftStatus.PositionY` segue | `XSidebarPanel.getHeightForWidth`, `XSidebar.requestLayout` | wiki Sidebar for Developers | medio | medio | v0.8, solo se S1 dice che 436 du non ci stanno | Risposte prende lo spazio liberato; rischio sfarfallio o ricostruzione: spike S6 |
| 14 | Riepilogo a sezioni fisse: Calcoli, Riferimenti verificati, Allegati citati, Avvertenze, Da completare | `render_summary` | CoCounsel change summary | piccolo | basso | v0.8 | Si legge come checklist prima di Verifica citazioni; cambia le attese dell'e2e |
| 15 | Pulsazione durante il passo 3 (ProgressBar che avanza a ogni evento) | `UnoControlProgressBarModel` | Copilot | piccolo | basso | v0.8, se il log non basta | Il core non manda totali (`protocol.py`): una barra "vera" sarebbe inventata |
| 16 | Campi tipizzati: un `DateField` gemello per riga mostrato quando il catalogo dice `tipo = data`; niente `CurrencyField` | `UnoControlDateFieldModel` (Date, Dropdown) | Henchman filtri | medio | medio | v0.8 | 8 controlli nascosti in più; serve un catalogo affidabile; spike S12 |
| 17 | Righe `FixedHyperlink` per le partizioni del passo 4 (8 pre-create, URL vuoto) | `UnoControlFixedHyperlinkModel` + `XActionListener` | Navigator | medio | medio | v0.8 | Un clic scatta sempre, niente stato di selezione; spike S8 |
| 18 | Roadmap a quattro item come indicatore (Interactive = False) | `UnoControlRoadmapModel` (CurrentItemID, Complete) | wizard di LibreOffice | medio | medio | dopo, solo se il prefisso di stato non basta | Costa circa 50 du e uno spike di resa (S7); il flusso non torna indietro |
| 19 | Pulsante di toolbar e voce di menu che aprono il deck e espandono Redazione | `Addons.xcu` + `XSidebarProvider.setVisible`, `XDeck.activate(True)`, `XPanel.expand(True)` | Legora e Harvey add-in | medio | basso | dopo | Il comando `.uno` per un deck custom non è confermato (S10): si fa da codice |
| 20 | Deck dedicato "LibreLex Redazione" con Redazione e Risposte | `Sidebar.xcu` DeckList, DeckId | Navigator, Style Inspector | piccolo | medio | dopo, se il collapse non basta | Solo configurazione; piena altezza senza la danza dei collapse |
| 21 | Passo 4 come revisione: "Allega norme citate" (il core ha `insert_norm`), "Cosa manca" che precompila Riprendi | controlli esistenti + core | Copilot Coaching; Lexis Get Cited Docs | medio | basso | dopo | Lavoro di core e ricetta, non di pannello |

Nota sulle inserzioni come revisioni: nessun interruttore da aggiungere, sono già revisioni firmate "LibreLex" (`document.py`). Va solo detto nel README del Task 6.

## 5. Schizzo dei quattro passi

Contratto invariato: larghezza 190 du (inner 182, colonne da 89), `MARGIN` 4, area 404 (y 4..408), `DraftStatus` a 412..432, totale **436 du** (test: ≤ 440). Le uniche differenze rispetto a `layout.py` oggi: le cinque sezioni diventano `FixedLine` (stessa altezza 10, stesse y), nessun `TextColor`, `Continue` mobile, `TabIndex` progressivo. I fondi dei passi restano 370, 320 (massimo), 322, 300.

**Condiviso**
- y 412 · `DraftStatus` FixedText 20 · "Passo N di 4 · <azione>" oppure "In attesa del tuo consenso: …" oppure l'ultimo errore.
- Titolo del pannello (best effort): "Redazione · N/4 <nome>".

**Passo 1 · Atto e dati** (fondo 370; v0.8 altezza propria 398)
- y 4 · `TemplateSearch` Edit 14 (w 138) | `TemplateRefresh` "Cerca" 40×14
- y 22 · `Template` ListBox dropdown 14
- y 40 · `TemplateNotes` FixedText 20 (colore del tema)
- y 64 · `FieldsLabel` FixedLine 10 "Campi del modello"
- y 78 · 8 × [`FieldLabelN` FixedText (w 72) | `FieldN` Edit] 14 ciascuna, senza gap, fino a 190 (righe oltre il conteggio nascoste)
- y 194 · `NotesLabel` FixedLine 10 "Fatti e note"
- y 208 · `Notes` Edit multilinea 30
- y 242 · `AttachmentsLabel` FixedLine 10 "Allegati del fascicolo (Doc. 1, 2, …)"
- y 256 · `Attachments` ListBox 36 ("Doc. 1 · fattura_12.pdf (12.300 caratteri)")
- y 296 · `AttachmentAdd` "Aggiungi…" | `AttachmentRemove` "Togli" 16 (Togli attivo solo con una riga scelta)
- y 316 · `ReferenceInfo` FixedText 16 (w 94) | `ReferenceBrowse` "Sfoglia…" 40×14 | `ReferenceClear` "Rimuovi" 40×14
- y 336 · `LetterheadLabel` FixedText (w 60) | `Letterhead` ListBox dropdown | `LetterheadAdd` "Aggiungi…" 40×14, riga 14
- y 354 · `Start` Button 16 a tutta larghezza "Avvia redazione" → fondo 370
- Focus di ingresso: `TemplateSearch`.

**Passo 2 · Domande** (fondo 320 con otto domande; v0.8 altezza propria 436 per lo slot del consenso)
- y 4 · `QuestionsHint` FixedText 20
- y 28 · 8 × [`QuestionLabelN` FixedText 20 + `AnswerN` Edit 14] = 34 per riga, fino a 300 (righe oltre N nascoste)
- y 28 + N·34 + 4 · `Continue` Button 16 "Continua" (con otto domande: y 304); nascosto mentre un consenso pende
- y 338 · `DraftConsentText` FixedText 30 (prima riga in grassetto "Il modello vuole leggere:")
- y 372 · `DraftConsentDocument` Button 16 a tutta larghezza
- y 392 · `DraftConsentOnce` | `DraftConsentDeny` 16 → fondo 408; i quattro controlli visibili solo mentre pende
- Focus di ingresso: `Answer1`; con consenso pendente: `DraftConsentText`.

**Passo 3 · Redazione in corso** (fondo 322; v0.8 altezza propria 436)
- y 4 · `Log` Edit sola lettura, multilinea, VScroll + AutoVScroll, 200 ("Inserito: Premesse in fatto"; v0.8: "14:33 ✓ Inserito: …")
- y 208 · `ExpectedLabel` FixedLine 10 "Partizioni attese"
- y 222 · `Expected` ListBox 80 ("✓ Intestazione", "· Premesse", …; clic: salto)
- y 306 · `DraftCancel` Button 16 "Annulla" (attivo mentre il core lavora, disabilitato mentre un consenso pende) → fondo 322
- y 338..408 · lo stesso slot del consenso del passo 2
- Focus di ingresso: `DraftCancel`.

**Passo 4 · Fine** (fondo 300; v0.8 altezza propria 328)
- y 4 · `PartitionsLabel` FixedLine 10 "Partizioni inserite"
- y 18 · `Partitions` ListBox 60 (stesso render del passo 3; clic: salto, selezione azzerata dopo)
- y 82 · `Summary` Edit sola lettura 140 (v0.8: sezioni Calcoli, Riferimenti verificati, Allegati citati, Avvertenze, Da completare)
- y 226 · `VerifyAct` Button 16 "Verifica citazioni"
- y 246 · `ResumeInput` Edit 14 (istruzione libera, facoltativa)
- y 264 · `Resume` Button 16 "Riprendi"
- y 284 · `NewDraft` Button 16 "Nuova redazione" → fondo 300
- Focus di ingresso: `ResumeInput`.

Ordine di tabulazione per passo: i controlli del passo dall'alto in basso, lo slot del consenso prima di `Continue` quando pende, `DraftStatus` senza tabstop. Nessun `DefaultButton` in nessun passo.

## 6. Cosa non fare e perché

- **Tab (`UnoControlTabPageContainerModel`) per i quattro passi.** Il flusso è lineare e le transizioni le decide il modello (3 → 2 → 3 → 4); i tab invitano a cliccare il passo 4 durante il 3; servono pagine `TabPage` con contenitori propri; resa fuori da un dialogo non documentata.
- **Grid per gli allegati.** Tre colonne in 182 du troncano comunque il nome; servono `DefaultGridDataModel`, `DefaultGridColumnModel` e un listener senza precedenti Python; resa e dark mode non verificati. Una riga formattata in ListBox porta le stesse informazioni con codice già cablato.
- **Quattro pannelli, uno per passo, ordinati con `OrderIndex`.** L'avvocato ha chiesto meno pannelli; quattro barre del titolo e quattro stati di collapse gestiti dal deck; `ContextList` è per contesto, non per stato della redazione.
- **`GroupBox` intorno alle sezioni.** Mangia spazio su quattro lati in una colonna da 170 a 190 du; `FixedLine` dà la stessa struttura a costo zero.
- **Colori fissi, righe di log colorate, icone sui bottoni.** I colori sono il rischio dark mode che la ricerca non ha potuto escludere; `TextColor` è per controllo, non per riga; SVG per `ImageURL` non confermato e PNG richiederebbe varianti HiDPI e per tema. I marcatori ✓ → ? ✗ portano lo stato in entrambi i temi.
- **Pittura custom, HTML, controlli creati a runtime.** Nessun esempio Python di pittura su un peer; nessun controllo HTML trovato; l'inserimento a runtime funziona ma aggiunge un percorso di relayout dove la visibilità basta.
- **`DefaultButton` su Avvia, Continua o i bottoni di consenso.** Un Invio da una casella di testo avvierebbe un inserimento nel documento, manderebbe risposte a metà o darebbe un consenso. La L. 132/2025 fa del controllo esplicito del professionista il punto.
- **ProgressBar con un totale.** Il core non lo manda (`protocol.py`); la lista delle partizioni con ✓ è un progresso onesto.
- **Pannello chat al posto della procedura.** La scelta del 19 settembre è una procedura guidata; Copilot Draft, Harvey e Robin confermano che redigere è modulo più vista di attività, non chat.
- **Dividere il passo 1 in "Atto" e "Fascicolo".** Un clic in più a ogni redazione per risparmiare spazio che il passo 1 non deve risparmiare (370 di 404).
- **Nascondere la barra del titolo del pannello.** Non documentato; l'unica via alla piena altezza è un deck a pannello singolo (raccomandazione 20, dopo).
- **Spostare adesso lo slot del consenso in alto o aggiungere una riga di intestazione.** Entrambe le idee della proposta A hanno senso, ma cambiano tabelle e test del Task 3 e portano il totale a 440; la misura di S1 dirà se servono. Con il prefisso di stato e il consenso "modale" il valore è coperto a costo zero.

## 7. Domande aperte e spike da fare

Ogni spike dice cosa verificare e come. S1, S2, S3, S4, S5 e S11 stanno nel field test del Task 5; gli altri sono build usa e getta nel profilo di sviluppo, fuori dal piano.

- **S1 · du → px e altezza disponibile.** Cosa: quanti pixel sono 436 du sul Mac dell'avvocato e quanti pixel ha il deck con Azioni e Citazioni collassati. Come: in `getHeightForWidth` e `windowResized` scrivere nel log di estensione `convertSizeToPixel(Size(0, 436), APPFONT).Height` e `window.getPosSize().Height`; leggere i numeri dopo il field test. Decide la raccomandazione 13.
- **S2 · Titolo del pannello.** Cosa: `frame.getController().getSidebar().getDecks().getByName("LibreLexDeck").getPanels().getByName("LibreLexRedazionePanel").setTitle(...)` funziona dal codice del pannello; la barra del titolo si ridisegna senza `requestLayout()`; un pannello ricostruito (cambio deck e ritorno) mostra di nuovo il titolo giusto dopo `_replay`. Come: field test, passando dal passo 1 al 3 e cambiando deck.
- **S3 · Resa di `FixedLine` nella sidebar.** Cosa: la riga con etichetta si vede nel peer della sidebar su macOS, in chiaro e in scuro, e non copre il testo. Come: screenshot del passo 1; ripiego automatico a `FixedText` se non si vede (stessi nomi, stessa geometria).
- **S4 · Dark mode.** Cosa: FixedText, Edit, ListBox, Button e la FixedLine restano leggibili con macOS in dark mode. Come: due screenshot per passo (chiaro e scuro) allegati al field test; verificare anche lo stato aggiornato del meta bug 118017 su bugs.documentfoundation.org.
- **S5 · Tastiera.** Cosa: `TabIndex` è rispettato in una finestra container (non dialogo); i controlli nascosti sono saltati; `setFocus` al cambio passo funziona. Come: field test, Tab attraverso il passo 1 e il passo 2 con tre domande.
- **S6 · `requestLayout()`.** Cosa: la chiamata fa solo richiedere le altezze (non ricostruisce il pannello); nessuno sfarfallio su macOS; Risposte prende lo spazio liberato. Come: build usa e getta che alterna 328 e 436 du a ogni `set_step`, con un contatore in `__init__` per vedere se il pannello viene ricreato.
- **S7 · Roadmap.** Cosa: si disegna nel peer della sidebar; altezza necessaria (stima 48 a 50 du); etichette non troncate a 170 du; sfondo e testo leggibili in dark mode (il default dello sfondo va letto sulla pagina IDL, non è nei findings). Come: build usa e getta con quattro item, `Interactive = False`.
- **S8 · `FixedHyperlink`.** Cosa: con un `XActionListener` registrato un clic non tenta di aprire l'URL vuoto; otto righe da 10 du costano quanto la ListBox da 80. Come: build usa e getta nel passo 4.
- **S9 · `DefaultButton` in una finestra container.** Cosa: scatta con Invio o no. Come: solo se un giorno lo si vorrà; oggi la raccomandazione è non usarlo.
- **S10 · Comando `.uno` per il deck custom.** Cosa: esiste un `.uno:` generato per `LibreLexDeck` invocabile da `Addons.xcu`, oppure serve `XDeck.activate(True)` da un job. Come: macro Basic che prova il dispatch e, in mancanza, il percorso via `XSidebarProvider`.
- **S11 · Salto durante l'inserimento.** Cosa: un clic su `Expected` mentre il modello scrive non sposta il punto in cui `insert_markdown` inserisce. Come: leggere in `document.py` se l'inserimento usa il cursore di vista o un cursore di testo proprio; se usa quello di vista, il click-to-jump nel passo 3 va disabilitato mentre `busy`.
- **S12 · Tipi del catalogo.** Cosa: quanti modelli dichiarano `tipo = data` in modo affidabile. Come: conteggio sul catalogo del core prima di adottare i `DateField`.
- **S13 · Drag and drop su macOS.** Cosa: `XDropTarget` sul peer AWT della sidebar riceve `text/uri-list`. Come: già nel field test del piano (drop di un PDF).
- **S14 · VoiceOver.** Cosa: i controlli AWT del pannello sono letti. Come: dopo, con VoiceOver attivo sul passo 1.

## 8. Fonti

API e documentazione LibreOffice
- https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XSidebarPanel.html
- https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XSidebar.html
- https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XPanel.html
- https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XDeck.html
- https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1ui_1_1XSidebarProvider.html
- https://wiki.openoffice.org/wiki/Sidebar_for_Developers
- https://wiki.documentfoundation.org/Design/Guidelines/SideBar
- https://flywire.github.io/lo-p/46-Addons.html
- https://ask.libreoffice.org/t/solved-any-document-explaining-addon-xcu-in-an-extension/120315
- https://help.libreoffice.org/Common/Showing,_Docking_and_Hiding_Windows
- https://help.libreoffice.org/latest/en-US/text/shared/guide/accessibility.html
- https://lists.freedesktop.org/archives/libreoffice-ux-advise/2024-May/045906.html
- https://www.libreoffice.org/assets/libocon2020/Slides/LibreOfficeCon-2020-NativeGtkWidgets.pdf
- https://dev.blog.documentfoundation.org/2023/11/25/libreoffice-extensions-with-python-part-1/
- https://docs.libreoffice.org/extensions.html

Controlli AWT
- https://wiki.openoffice.org/wiki/Documentation/DevGuide/Basic/Creating_Dialogs_at_Runtime
- https://www.openoffice.org/api/docs/common/ref/com/sun/star/awt/XControlContainer.html
- https://www.openoffice.org/api/docs/common/ref/com/sun/star/awt/XActionListener.html
- https://wiki.openoffice.org/wiki/Danny.OOo.Listeners.ListenerProcAdapters.py
- https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlRoadmapModel.html
- https://wiki.openoffice.org/wiki/Documentation/DevGuide/GUI/Roadmap_Control
- https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1tab_1_1UnoControlTabPageContainer.html
- https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1grid_1_1UnoControlGridModel.html
- https://wiki.openoffice.org/wiki/API/UNO_AWT/Grid_Control
- https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1tree_1_1TreeControlModel.html
- https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlFixedTextModel.html
- https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlEditModel.html
- https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlFixedLineModel.html
- https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlFixedHyperlinkModel.html
- https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlDateFieldModel.html
- https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlCheckBoxModel.html
- https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlButtonModel.html
- https://api.libreoffice.org/docs/idl/ref/servicecom_1_1sun_1_1star_1_1awt_1_1UnoControlModel.html
- https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1awt_1_1XPaintListener.html
- https://forum.openoffice.org/en/forum/viewtopic.php?t=19891
- https://github.com/LibreOffice/core/blob/master/toolkit/qa/complex/toolkit/UnitConversion.java
- https://forum.openoffice.org/en/forum/viewtopic.php?f=47&t=62176
- https://forum.openoffice.org/en/forum/viewtopic.php?t=70747
- https://github.com/eellak/gsoc2018-librecust/wiki/Toolbar-customization
- https://libreoffice-bugs.freedesktop.narkive.com/E09e5wFX/bug-51733-update-icons-for-high-resolution-hidpi-retina-display

Bug e piattaforma macOS
- https://www.mail-archive.com/libreoffice-bugs@lists.freedesktop.org/msg1010058.html
- https://www.mail-archive.com/libreoffice-bugs@lists.freedesktop.org/msg1014856.html
- https://bugs.documentfoundation.org/show_bug.cgi?id=138122

Precedenti (estensioni)
- https://github.com/mihailthebuilder/librethinker-extension
- https://extensions.libreoffice.org/en/extensions/show/99471
- https://github.com/KeithCu/writeragent
- https://github.com/ariharasudhanm/libreoffice-ai-assistant
- https://extensions.libreoffice.org/en/extensions/show/41988
- https://templates-arm.libreoffice.org/en/extensions/show/grammalecte
- https://www.linuxlinks.com/texmaths-latex-equation-editor-libreoffice/
- https://github.com/allotropia/libreoffice-sidebar-extension
- https://github.com/kelsa-pi/unodit/wiki/Create-sidebar-extension
- https://github.com/hanya/SidebarByMacros
- https://www.collaboraonline.com/blog/cool-26-04-release/

Copiloti legali e Word
- https://support.microsoft.com/en-us/copilot-word
- https://techcommunity.microsoft.com/blog/microsoft365insiderblog/improve-your-content-using-coaching-with-copilot-in-word-for-the-web/4265714
- https://legora.com/blog/introducing-legora-word-actions
- https://legora.com/product/workflows
- https://www.harvey.ai/blog/improved-word-experience
- https://www.harvey.ai/blog/harveys-new-drafting-tools-meet-you-where-you-work
- https://spellbook.com/learn/word-add-ins-for-enhanced-legal-drafting
- https://www.spellbook.legal/
- https://legal.lexisnexis.com/AI-Powered-Drafting
- https://www.lawnext.com/2024/07/how-it-works-a-demo-of-henchman-generative-ai-driven-contract-drafting-and-negotiation-within-word.html
- https://www.thomsonreuters.com/en-us/help/cocounsel/legal/cocounsel-for-microsoft-word/about-transactional-drafting
- https://legal.thomsonreuters.com/blog/legal-drafting-meets-generative-ai/
- https://robinai.com/news-and-resources/robin-university/word-add-in-an-intelligent-ai-sidekick-for-contract-review
- https://www.luminance.com/press/luminance-enhances-the-legal-industrys-only-100-ai-autonomous-contract-negotiation-tool-to-show-the-why-behind-every-decision-and-opens-it-to-the-entire-enterprise/
- https://www.vaquill.ai/blog/luminance-review-honest-assessment
- https://simpliciter.ai/
- https://www.ecnews.it/legale/mondo-professione/ai-digitalizzazione/intelligenza-artificiale-responsabilita-aggravata-nella-redazione-degli-atti-giudiziari/

Fatti di progetto (worktree `drafting-workbench`)
- `docs/superpowers/specs/2026-09-20-drafting-workbench-design.md` (§1 verifica di `XPanel.collapse` e `XSidebarProvider`, §3, §8)
- `docs/superpowers/plans/2026-09-20-drafting-workbench-extension.md` (Task 3, 5, 6)
- `extension/librelex_ext/layout.py` (tabella: totale 436, fondi 370/320/322/300, consenso 338..408, stato 412)
- `extension/librelex_ext/panel.py` (righe 97 e 98: `KeyError` su `Questions`; `getHeightForWidth`, `_build_controls`, `_apply_layout`)
- `extension/librelex_ext/document.py` (righe 555 e 647: inserzioni con `RecordChanges` e identità LibreLex)
- `core/src/librelex_core/protocol.py` (classe `Status`: solo `request_id` e `text`)
- `scratchpad/probe.out` e `probe.py` (probe headless su 26.8, 2026-09-20)
