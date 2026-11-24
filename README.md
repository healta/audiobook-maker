# audiobook-maker

Drop an English book into a folder and get a finished audiobook back: one `.m4b` with chapters, cover and a report.
It runs on its own hardware with the [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) voice model. Nothing is uploaded; the only thing sent anywhere is the author's name, to Wikidata, to choose a male or female voice (this can be turned off).

## Folders

Everything lives in one folder, mounted as `/data`:

| Folder | What it is for |
|---|---|
| `input` | Put books here: `.epub`, `.txt`, `.html`, or a `.zip` with one HTML or text file. They are picked up automatically, one at a time. |
| `in-progress` | Temporary files. `status.txt` shows the current book, percentage and time left. Work survives restarts. |
| `output` | `Author - Title/` with the `.m4b`, `report.txt`, the cover and the original book. Books that cannot be narrated go to `output/_failed` with the reason. |
| `config` | `config.yaml` (voices, speed, intro...), `authors.yaml` (your corrections), `lexicon.yaml` (your pronunciations). Created on first start. |

## Dashboard

`http://your-server:30480` lists the book in progress with the time left, the queue, and the finished books. It is a single read-only page without logins, meant for your home network: do not forward its port to the internet. Change the port in `compose.yaml` (in both places), or switch the page off with `DASHBOARD_PORT: 0` under `environment`.

## Installing on TrueNAS (24.10 or 25.04)

TrueNAS 25.10 and newer ship an NVIDIA driver that no longer runs GTX 10-series cards; there this image falls back to the CPU.
`tank` stands for your pool's name everywhere below. Commands go into System > Shell.

1. **Apps pool:** Apps > Configuration > Choose Pool, if you have not chosen one yet. The image takes about 11 GB there, and about 2.5 GB of memory while it works.
2. **GPU driver:** Apps > Configuration > Settings > tick *Install NVIDIA Drivers* > Save. Then `nvidia-smi` should list the card. If it does not, check that the card is not reserved under System > Advanced Settings > *Isolated GPU Device(s)*, and restart the server.
3. **Folder:** Datasets > your pool > Add Dataset, name `audiobooks`, preset *Apps*. This preset lets apps (group 568) write to it.
4. **Network share, to copy books from your PC:** Shares > Windows (SMB) Shares > Add, path `/mnt/tank/audiobooks`. Not needed if the dataset lies inside one you already share.
5. **App:** Apps > Discover Apps > three dots > *Install via YAML*. Name: `audiobook-maker`. Custom Config: the contents of `compose.yaml`, with your pool in place of `POOL`. Save. The first start downloads about 4 GB.
6. **Check the GPU:**

   ```sh
   sudo docker exec audiobook-maker python -m app check
   ```

   It prints whether the GPU is used and how fast it is. If it says CPU, it also says why; see Troubleshooting.

## Updates

Every change to the program on the `main` branch is tested by GitHub: the unit tests, then a tiny book narrated with the new image. Only if that works is it published as `:latest`. TrueNAS looks for new images once a day and then shows *Update* on the app; a click downloads the changed part (usually well under 1 MB) and restarts it. A book in progress carries on where it was.

| To... | do this |
|---|---|
| look for an update right away | `sudo midclt call app.image.op.check_update`, then reload the Apps page |
| update without waiting for the button | `sudo midclt call -job app.pull_images audiobook-maker '{"redeploy": true}'` |
| go back to an older version | in the app's YAML, put that version's tag in place of `latest`, for example `:sha-1234567`; the tags are listed under *Packages* on GitHub |
| stop the daily check | Apps > Configuration > Settings |

To build the image yourself instead: `docker build -t audiobook-maker .`, and use `image: audiobook-maker` with `pull_policy: never` in `compose.yaml`.

## Using it

Copy a book into `input`. That's all.

* **Voice:** the author's recorded gender is looked up on Wikidata, and one of your voices of that gender is picked at random. Unknown or mixed authors use all voices. Nothing is guessed from first names.
* **Choose yourself:** put a tag in the file name, such as `Emma [female].epub` or `Emma [bm_fable].epub`.
* **Wrong author gender:** add a line to `config/authors.yaml`.
* **Mispronounced word:** add a line to `config/lexicon.yaml` and put the book in again.
* **Other voices:** `docker exec audiobook-maker python -m app voices` lists them; `... sample am_onyx` writes a sample to `output`. Then edit `config.yaml`.
* **See what would be read, without narrating:** `docker exec audiobook-maker python -m app preview "/data/input/book.epub"`.

Footnotes, page numbers, picture captions, tables of contents, Project Gutenberg's own header and licence, and similar page furniture are left out. `report.txt` lists everything that was not read.

MOBI, AZW3 and PDF are not supported: convert them to EPUB first (Calibre does this). Copy-protected EPUBs cannot be read.

## Before you publish a recording

`report.txt` has a RIGHTS section. "Public domain in the USA" does not cover other countries: much of the world protects a work for 70 years after the death of its author *and* translator. Some Project Gutenberg books are still in copyright; the report flags those that say so. Project Gutenberg's name is a trademark, which is why its header and licence are not read out.

## Troubleshooting

| What you see | What to do |
|---|---|
| The container does not start, "could not select device driver nvidia" | Install the NVIDIA driver (step 2), or delete the `deploy:` block to use the CPU. |
| "cannot write to /data/..." in the log | Give user 568 write access to the folder, or change `user:` in the YAML to its owner. |
| "no NVIDIA GPU is visible" | `nvidia-smi` must work in the server's shell first (step 2). Then delete the app and install it again. Still nothing: run `nvidia-smi -L`, and in the YAML put that `GPU-...` id in place of `all` after `NVIDIA_VISIBLE_DEVICES:`, and replace `count: all` with `device_ids: ["GPU-..."]`. |
| "port is already allocated" | Another app uses 30480. Change it in `compose.yaml`, in both places. |
| A book ended up in `_failed` | Read `why.txt` next to it. Move the book back into `input` to try again. |

## Development

`python -m unittest discover -s tests` runs the text tests (needs `lxml`, `PyYAML` and `numpy` only).
`bash tests/smoke.sh IMAGE` narrates a tiny book with a built image. `.github/workflows/publish.yml` does both and publishes the image, on every push to `main` that changes the program. Keep the base image's digest, the requirements and the models as they are unless you mean to change them: everything below them in the `Dockerfile` is a small layer, everything above is several gigabytes.

## Licence

The code in this repository is under the [BSD Zero Clause License](LICENSE): do whatever you like with it. The image also contains other people's software under their own licences, some of it GPL; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
