# ctrnf-skins-builder

Workspace para **reemplazar el modelo de la skin por defecto de un piloto** de CTR Nitro-Fueled
(port de PC "OCTR", carpeta portable del usuario) por un modelo 3D que trae el usuario
(FBX / glTF / DAE / OBJ / XPS / escaneos). Los formatos del juego ya están resueltos en `tools/`;
no hay que volver a estudiarlos. Python 3 sin dependencias (`python -I`) + Blender 5.2 en segundo plano.

Es un repositorio público: cualquiera lo clona, abre Claude Code en él y pide
"toma este modelo y mételo al juego reemplazando a <piloto>". Responde en el idioma del usuario.

## Qué va en este archivo

`CLAUDE.md` es el manual para atender esas peticiones: **cómo se procede para X** (un tipo de
modelo, un piloto, un problema gráfico y su solución, un paso del flujo). Modifícalo solo para
añadir o corregir instrucciones de ese tipo, escritas en general y válidas para cualquier usuario.
Nunca apuntes aquí historial ni estado de una instalación concreta: qué mods tiene alguien, fechas,
qué se probó con tal personaje, rutas personales, nombres elegidos por un usuario. Tampoco guardes
memorias de Claude Code sobre este proyecto: lo que valga para todos va aquí; lo demás, a ningún sitio.

## Primer paso de cada conversación

1. Si no existe `config.json`, pide al usuario la **carpeta portable del juego** (la que contiene
   `Crash™ Team Racing Nitro-Fueled.exe`, `mods/`, `python/`, `scripts/` y la carpeta del juego
   `CUSA14876-1.21` o `CUSA13795…` con `eboot.bin` y `archives/`). Copia `config.example.json`
   a `config.json` y rellena `portable`, `archives` (= `<juego>/archives`), `mods`, `blender`.
2. Lee `config.json` y úsalo en todos los comandos.

## Estructura

| Ruta | Qué es |
|---|---|
| `tools/character_mod.py` | CLI: `export`, `info`, `build` (ver su docstring). Tabla `CHARACTERS`. |
| `tools/blender_fit.py` | Script de Blender: ajusta el modelo al esqueleto del piloto, atlas de texturas, LODs reducidos, renders. Docstring = referencia de `fit.json`. |
| `tools/model.py` `igz.py` `texture.py` `gltf.py` `importer.py` `pak.py` | Formatos del juego (IGZ v10 PS4, BC1/BC3/BC5 con tiling PS4, PAK IGA v13). |
| `tools/lib/` | Copia de scripts del launcher OCTR que usan las herramientas (lector PAK, validador `mod.json`). |
| `tools/ui_mod.py` | `names` (mod "Nombres de pilotos"), `portrait` (se añade a un mod ya hecho), `merge`, `repack`. Tabla `UI`. |
| `tools/check_launcher.py` | Simula la preparación de mods del launcher (sin abrir el juego). |
| `tools/blender/` | Inspección/revisión en Blender: `inspect.py`, `mats.py`, `seated.py`, `closeup2.py`, `xps_import.py`. |
| `tools/unzip.py` | Extrae zips de forma segura (rechaza rutas `..`). |
| `examples/*.json` | `fit.json` de referencia por tipo de modelo. Su `"model"` apunta a rutas viejas: cámbialo. |
| `work/` | Trabajo por modelo: `work/<nombre>/src`, `fit.json`, salidas `.glb`/`.png`, renders; fuentes de mods en `work/mods/`. |

Comandos: `B` = ruta de Blender de `config.json`, `A` = `archives`, `M` = `mods`.

## Pilotos soportados (`CHARACTERS` en `character_mod.py`)

| Clave | Piloto (nombre ES) | Slot de material | LODs | Notas |
|---|---|---|---|---|
| `crash` | Crash | `Cloth` | 0-4 | update.pak pisa LOD 1/3/4 |
| `coco` | Coco | `Coco` | 0-4 | pequeña: un humano realista queda diminuto y cabezón |
| `hunter` | Cazador (Hunter) | `Body` | 0-4 | PAKs anidados en update2.pak; piernas digitígradas, cuello largo |
| `tawna` | Tawna | `Clothes` | 0-3 | PAKs anidados en update.pak; alta |
| `geary` | Geary | `Rubber` | 0,1,3,4 | robot con pose T; tiene mapa de brillo (`--flat=emission`) |
| `cortex` | Neo Cortex | `CortexDriver_Body` | 0-4 | cabeza enorme, piernas cortas, brazos largos; update.pak pisa LOD 3/4 |
| `pura` | Pura | `PuraDriver_Body` | 0-3 | **cuadrúpedo** (ver abajo); LOD 3 sin Body → `lod_slot` `PuraDriver_Fur_Lod2`; relieve: `--flat=height` |
| `stew` | Stew (`DriverSTW`) | `Clothes` | 0-4 | PAKs anidados en update2.pak; alto, piernas cortas, barriga, **cuello de 40 cm** (cabeza rígida en `Bone_Neck`). No sirve para humanos |
| `ami` | Ami | `Outfit` | 0-4 | PAKs anidados en update.pak; humana alta (1,8 m), proporciones normales; LOD 0 pequeño (14 016) |
| `megumi` | Megumi | `Outfit` | 0-4 | PAKs anidados en update.pak; humana 1,66 m, piernas de adulto, pies de puntillas; LOD 0 16 768. **Mejor opción para humanos de tamaño normal** |
| `pasadena` | Pasadena O'Possum (`DriverPOM`) | `UpperBody` | 0-4 | PAKs anidados en update2.pak; esqueleto casi igual que Megumi (1,69 m), LOD 0 18 550 |

**Añadir otro piloto:** busca su nombre interno en `looseData/systemData_es.lng` (dentro de
`update2.pak`; p. ej. "Cazador" → `DriverHunter`), sus archivos `Driver<X>_Outfit_Default_skins.pak`,
`..._Cutscene_skins.pak` (LOD 0) y `..._materials.pak` (en `archives/` o anidados como
`archives/<nombre>.pak` dentro de `update.pak`/`update2.pak`; `pak.open_archive` los encuentra
igual). Lista sus `actors_stripped/*.igz` para ver el patrón de nombres de LOD, y usa
`character_mod.material_images()` sobre el `materialinstances/...igz` para elegir el slot (el
material del cuerpo; evita los metálicos/pelo/fur). Añade la entrada con `character(...)`.

## Flujo para un modelo nuevo

1. **Extraer**: `python -I tools/unzip.py <zip> work/<nombre>/src` (repite con zips internos).
   `.rar`: `7z x -o<dir> <archivo>` (7-Zip en scoop).
2. **Inspeccionar** el modelo: `"$B" -b --factory-startup --python tools/blender/inspect.py -- <modelo>`
   (objetos, armatures, huesos con posición, mallas, materiales). `tools/blender/mats.py`: colores
   base, imágenes y rangos UV por material. Averigua hacia dónde mira (nariz/pies) → `rotate_z`
   (el juego mira a +X; un modelo que mira a −Y lleva `90`).
3. **Referencia del piloto**: `python -I tools/character_mod.py export <piloto> "$A" work/<piloto>.glb`
   y mira sus huesos con `inspect.py` (todos usan `Bone_Pelvis`, `Bone_Spine1-4`, `Bone_Neck`,
   `Bone_neckB`, `Bone_Head`, `Bone_[LR]_{Clavicle,UpperArm,Forearm,Hand,Middle,Thigh,Calf,Foot,Toe0}`).
4. **Límites de memoria**: `python -I tools/character_mod.py info <piloto> "$A"` → pega la lista en
   `"lods"` del `fit.json` (con un 5 % de margen si el modelo es grande). Solo si no cabe.
5. **`fit.json`**: parte del ejemplo más parecido:
   - esqueleto propio normal (FBX/Valve/BotW): `gordon_on_hunter.json`, `link_on_tawna.json`;
   - piezas rígidas tipo N64: `mario_on_crash.json`;
   - escaneo sin esqueleto: `vaultboy_on_coco.json` (+ `vaultboy_joints_reference.json`);
   - esqueleto estilo Mixamo (`Hips`, `LeftArm`...), párpados cerrados: `sonic_on_cortex.json`;
   - bípedo sobre cuadrúpedo (Pura): `rigby_on_pura.json`;
   - malla sin esqueleto con pesos hechos por zonas: `jake_on_geary.json` + `jake_rig_weights.py`;
   - XNALara/XPS (`.mesh` + `.pose`, huesos tipo `arm left elbow`), con capa: `ezio_on_pasadena.json`.
     Convierte antes a glb con
     `"$B" -b --factory-startup --python tools/blender/xps_import.py -- <x.mesh> <out.glb> '<regex de grupos>'`
     (p. ej. `'^24_(\+|Body|Head)'`). Opciones: `'--cut=<prefijo de hueso>:<altura>'` corta en
     recto, `'--unweight=<prefijo>:<hueso>,<hueso>'` quita pesos. En rips XPS de Fortnite el grupo 27 son
     duplicados de reflejo y `-` piezas ocultas; el alfa de `_D.tga` es máscara (el importador lo quita).
     Fortnite: `"weld": 0.00001`. Tamaño = altura del piloto / altura del modelo, con grosor y piezas
     rígidas a la misma escala (proporciones normales).
6. **Ajustar**: `"$B" -b --factory-startup --python tools/blender_fit.py -- work/<piloto>.glb work/<n>/fit.json work/<n>/<n>.glb work/<n>/renders`
   Mira los renders (`front/side/quarter_model.png` vs `_game.png`) con la herramienta Read,
   sentado en el kart con `tools/blender/seated.py -- <out_lod0.glb> <atlas.png> <out.png> side|quarter|back`
   (sin caras traseras, como el juego)
   y primeros planos con `tools/blender/closeup2.py -- <glb> <atlas.png> <out.png> <ortho> "(x,y,z)" TEXTURE`.
   Itera escalas/anclajes hasta que se vea bien. Manda los renders al usuario antes de construir.
7. **Construir**: `python -I tools/character_mod.py build <piloto> "$A" work/<n>/<n>.glb work/mods/<Nombre del mod> --texture=<Slot>=work/<n>/<n>.png --flat=normal --flat=composite [--flat=emission]`
   (usa solo los `<n>_lod<k>.glb` que existan; imprime vértices/bytes por LOD frente a los del juego
   y **se niega a escribir** si alguno pasa del original: falta un `_lod<k>.glb` porque `blender_fit`
   falló, o los `"lods"` son altos).
8. **Retrato** (solo si el usuario da una imagen): `python -I tools/ui_mod.py portrait <piloto> "$A" work/portraits/<n>.png work/mods/<Nombre del mod>`
   (PNG RGBA cuadrado, fondo transparente, **boca abajo**: así guarda el juego los retratos).
   `character_mod build` rehace la carpeta del mod y borra el retrato: vuelve a pasar `portrait`.
   **Nunca un retrato renderizado del modelo**: sin imagen del usuario, se queda el original.
   La selección de personaje usa `custo_ico_char_racer_NN` (material `Racer_<X>` de
   `RacerPortraits_materials.igz`, copiado en cada `juicedomain_*.pak`), no `racerportrait` (HUD).
9. **Nombre**: `python -I tools/ui_mod.py names "$A" "work/mods/Nombres de pilotos" crash=Mario hunter="Gordon Freeman" ...`
   con la lista **completa** de pilotos cambiados (todos en un solo mod: el launcher no deja que dos
   mods toquen el mismo `systemData_<idioma>.lng`). Saca los nombres actuales del mod existente antes
   de rehacerlo.
10. **Unir en un solo pack**: todos los mods van juntos en un pack (por defecto "Crossover Skin Pack"):
    `python -I tools/ui_mod.py merge "$M/Crossover Skin Pack" work/mods/<cada mod> ... "work/mods/Nombres de pilotos"`.
    No dejes mods sueltos en `mods/`. Si `mods/` ya tiene mods sueltos de este repo, pregunta antes de
    moverlos a `<portable>/mod-state/removed/`.
11. **Comprobar**: `python -I tools/check_launcher.py "<portable>"` → debe listar los mods y decir
    `OK`. Si dice "A mod session is already running", el juego está abierto (normal).
12. El usuario prueba en el juego (activar en *Mods* del launcher, reiniciar el juego) y manda capturas.

## Reglas y soluciones conocidas

- **Memoria por piloto**: cada piloto tiene un pool fijo. Pasarse = crash al previsualizarlo
  (log `last_run_*.log` de la portable: `OOM ... HERO-0-HeroData-Driver<X>`, código 3). Usa `"lods"`;
  `Model.replace` ya compacta la geometría original sobrante.
- **No reduzcas si no hace falta**: si el modelo cabe, no pongas `"lods"`; la reducción estropea
  el modelo y el completo en todos los LODs se ve mejor.
- **Límite del launcher**: el parche de cada `.pak` (suma de payloads del pack sobre ese archivo)
  debe ser < 64 MB ("Mod archive overlay exceeds engine limits"). `pak.rebuild` conserva
  comprimidas las entradas no tocadas; mods viejos se arreglan con `ui_mod.py repack`.
- **Proporciones**: el cuerpo sigue las articulaciones del piloto (las animaciones mandan); la
  cabeza/manos/pies son rígidos con escala propia. Nada de cabezas enormes ni personajes diminutos,
  ni agrandar solo grosor/cabeza/manos: elige un piloto de estatura parecida (Coco/Crash pequeños,
  Tawna/Hunter altos, Megumi/Pasadena humanos normales).
- **Escaneos** (UV en cientos de islas): `"rebake": 2048` (UV nuevo + horneado con Cycles) antes de
  reducir, o salen grietas/rayas. `"cut_below"` quita peanas. Mano fundida al cuerpo → quítale los
  segmentos y pon sus huesos en `"bones"` al torso (va fija).
- **Rips de Fortnite**: `"weld": 0.00001` (vértices sueltos), `"flip_winding": true` (triángulos al
  revés: el juego descarta por giro y se ve transparente), `"by_position": ["dfrm_", "def_"]`
  (huesos auxiliares colgados de la columna), `"attach": {"pack": "spine_05"}` (mochila), y quita la
  lámina de la cara (`drop_objects`), cara pintada con `"decals"`.
- **Texturas**: filas de arriba primero (ctrnf-modkit las invierte: está mal). Mapas normales BC5.
  El color del slot se reemplaza con el atlas; `--flat=*` evita que se vea el relieve/brillo del
  piloto original. `--flat=composite` usa la media del original: en Geary es metal (`0,131,112`,
  G brillo, B metal) y el modelo sale metálico; para piel/tela usa `--composite=0,60,0` (mate).
- **Material sin imagen enlazada** (rips con las texturas aparte): `"images": {"material": "png"}`.
- **Ojos cerrados** (párpados pesados a huesos `Eyelid*`): `"drop_groups": ["Eyelid"]` quita esas
  caras y deja ver el globo ocular. Pupila transparente (alfa) → el atlas la pinta sobre el color
  base del material: `"base_colors"` con negro. Los renders `*_model.png` usan los materiales
  originales; para ver el atlas usa `closeup2.py` (con rutas absolutas).
- **Capas** (también colas de fajín y tela que cuelga de la espalda): no se cortan; van como parte
  de la espalda, como la capa de plástico de un muñeco. `"drape": {"bones": ["cape", "belt"]}`
  (prefijos de sus huesos): arriba sigue la columna, bajo la cadera pasa suave al muslo de su lado
  (`"hip"`) y en la rodilla a la pantorrilla (`"knee"`), solo por altura, así que sentado queda bajo
  las piernas sin romperse ni arrugarse; los pesos que el rip pone al brazo en el borde se ignoran
  (`"seam"`: desde esa parte de peso a la capa, 0.05, el vértice es todo capa). Si atraviesa el
  respaldo al respirar (el piloto se echa atrás), `"inset": 0.05` la acerca a la espalda baja sin
  meterla en el cuerpo. La tela `"drape"` no se reduce en los LODs (el forro asomaría por fuera).
  Revisa con `seated.py` `side`/`back`. Cortar con `--cut` a la altura del cinturón solo si el
  usuario lo pide.
- **Capas de tela dobles** fuera de `"drape"` (exterior + forro de otro color): al reducir se
  cruzan y asoma el forro; pinta el forro del color de fuera en una copia de las fuentes.
- **Huesos de ropa sin asignar** (cuellos, solapas, piezas colgadas del pecho): heredan la
  asignación de `"bones"` de su antepasado más cercano (`weight_target` en `blender_fit`). Si algo
  se estira hasta el asiento al sentarse, busca vértices con peso a un hueso lejano.
- **Pies**: los pilotos que pisan de puntillas (Ami, Megumi) necesitan `"align"` del pie a
  `Foot→Toe0`; un pie plano no llega al pedal.
- **Manos al volante**: si la mano del modelo es más corta que la del piloto, estira el antebrazo
  hasta `Bone_[LR]_Middle` y ancla ahí la mano (`"to": ["Bone_L_Middle"]`), como en `jake_on_geary.json`.
- **LODs reducidos** (`blender_fit` `reduced`): parten más vértices en las costuras, así que los
  `"lods"` llevan factores por nivel (p. ej. 0.9, 0.84, 0.8, 0.76, 0.8). Mira la salida de `build`:
  **ninguno por encima del juego**.
- **Pura es cuadrúpeda**: patas delanteras `Bone_[LR]_Thigh/Calf/Foot` (→ brazos del modelo,
  mano en `Foot` alineada a `Toe0`), traseras `Bone_[LR]_Thigh2/Calf2/Foot2` (→ piernas), columna
  horizontal `Bone_Pelvis` (atrás) → `Bone_Neck` (delante) (→ torso). Los renders estándar la
  cortan: mírala con `closeup2.py` ortho 2.8 en `(-0.4,0,0.5)`. Patas gruesas: `"radial"` por segmento.
  En el kart se sienta con la columna **vertical** y la cabeza de reposo mira abajo: una pieza
  rígida con solo `rotate_z` sale mirando al cielo. Alinea cabeza y cola (`"align"`) con la
  columna/cola de Pura, ancla la cabeza en `Bone_Neck` y adelanta el torso con `"offset": [0,0,-0.12]`
  (abajo en reposo = delante en el kart). Para previsualizar sentado: gira el reposo −80° en Y.
  Manos al volante: antebrazo hasta `Bone_[LR]_Foot` (más allá hace zigzag: Pura dobla la muñeca),
  mano anclada en `Foot` y grande (3.6) con `"align"` a `Foot→Toe0` y `"roll_from": [index_01,
  pinky_01]` → `"roll": [Bone_X_04_FrontToe, Bone_X_FrontToe]` (sin roll la palma queda de canto);
  dedos (`index/middle/pinky_0[123]`) en `"bones"` a `Bone_X_Toe0` para que se cierren al volante.
  Grosor del torso: `"radial"` 2.4 con cabeza 2.2.
- **Mods**: paquetes OCTR (`mod.json` con operaciones `archive_asset`). Nunca `update3.pak` sueltos
  (solo uno puede estar activo). Dos mods del mismo piloto chocan.
- **Launcher EU**: con la versión EU del juego (CUSA14876) el launcher original de OCTR oculta los
  mods. Si `check_launcher.py` o el launcher no listan el mod, revisa en la portable
  `scripts/mod_library.py`, `mod_packages.py` y `run.py`: hay que hacer que acepten el título EU
  (guarda copia `.bak` antes de tocarlos y pide permiso al usuario).
- **No borres** cosas del usuario sin pedírselo; mueve a `<portable>/mod-state/removed/`.
