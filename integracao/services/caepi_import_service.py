import csv
import gzip
import hashlib
import io
import logging
import time
import zipfile
import zlib
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Subquery
from django.utils import timezone

from integracao.models import CaepiImportacao, CaepiRegistro


logger = logging.getLogger(__name__)


class _LimitedReader(io.RawIOBase):
    """Limita o conteúdo descompactado sem carregá-lo integralmente em RAM."""

    def __init__(self, source, limit):
        self.source = source
        self.limit = limit
        self.total = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.source.read(len(buffer))
        if not data:
            return 0
        self.total += len(data)
        if self.total > self.limit:
            raise ValidationError('O conteúdo descompactado excede 350 MB.')
        buffer[:len(data)] = data
        return len(data)


class _GzipStream(io.RawIOBase):
    """Descompacta incrementalmente e ignora apenas bytes após o membro GZIP."""

    def __init__(self, source, chunk_size=1024 * 1024):
        self.source = source
        self.chunk_size = chunk_size
        self.decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        self.pending = bytearray()
        self.finished = False

    def readable(self):
        return True

    def readinto(self, buffer):
        while len(self.pending) < len(buffer) and not self.finished:
            chunk = self.source.read(self.chunk_size)
            if not chunk:
                if not self.decoder.eof:
                    raise gzip.BadGzipFile('Fluxo GZIP incompleto.')
                self.pending.extend(self.decoder.flush())
                self.finished = True
                break
            try:
                self.pending.extend(self.decoder.decompress(chunk))
            except zlib.error as exc:
                raise gzip.BadGzipFile('Fluxo GZIP inválido.') from exc
            if self.decoder.eof:
                self.pending.extend(self.decoder.flush())
                self.finished = True
        quantidade = min(len(buffer), len(self.pending))
        if not quantidade:
            return 0
        buffer[:quantidade] = self.pending[:quantidade]
        del self.pending[:quantidade]
        return quantidade


class CaepiImportService:
    MAX_UPLOAD_BYTES = 150 * 1024 * 1024
    MAX_EXTRACTED_BYTES = 350 * 1024 * 1024
    HASH_CHUNK_BYTES = 1024 * 1024
    INSERT_BATCH_SIZE = 1000
    WEB_BATCH_ROWS = 5000
    WEB_BATCH_SECONDS = 15
    STALE_AFTER = timedelta(minutes=10)
    REQUIRED_COLUMNS = {
        'NR Registro CA', 'DATA DE VALIDADE', 'SITUACAO', 'NATUREZA',
        'EQUIPAMENTO', 'DESCRICAO EQUIPAMENTO', 'MARCA CA', 'REFERENCIA',
        'COR', 'APROVADO PARA LAUDO', 'RESTRICAO LAUDO',
        'OBSERVACAO ANALISE LAUDO', 'NR LAUDO', 'NORMA',
    }
    RETAINED_MAPPING = {
        'NATUREZA': 'natureza',
        'EQUIPAMENTO': 'equipamento',
        'DESCRICAO EQUIPAMENTO': 'descricao_equipamento',
        'MARCA CA': 'marca',
        'REFERENCIA': 'referencia',
        'COR': 'cor',
        'APROVADO PARA LAUDO': 'aprovado_para',
        'RESTRICAO LAUDO': 'restricao',
        'OBSERVACAO ANALISE LAUDO': 'observacao_analise',
        'NR LAUDO': 'numero_laudo',
        'NORMA': 'norma',
    }

    @classmethod
    def enfileirar_previa(cls, *, uploaded_file, user):
        """Persiste o upload e devolve antes da importação pesada começar."""
        nome = uploaded_file.name or 'caepi.csv'
        if Path(nome).suffix.lower() not in {'.csv', '.txt', '.zip', '.gz'}:
            raise ValidationError('Envie o relatório em CSV, TXT, ZIP ou GZIP.')
        digest, tamanho_bytes = cls._fingerprint(uploaded_file)
        existing = CaepiImportacao.objects.filter(sha256=digest).first()
        if existing and existing.status == CaepiImportacao.Status.PROCESSANDO:
            if existing.atualizado_em > timezone.now() - cls.STALE_AFTER:
                return existing, False
            existing.status = CaepiImportacao.Status.INTERROMPIDA
            existing.erro = (
                'A execução anterior foi interrompida antes da conclusão. '
                'O processamento será reiniciado com o arquivo preservado.'
            )
            existing.finalizado_em = timezone.now()
            existing.save(update_fields=(
                'status', 'erro', 'finalizado_em', 'atualizado_em',
            ))
        if existing and existing.status not in (
            CaepiImportacao.Status.FALHOU,
            CaepiImportacao.Status.INTERROMPIDA,
        ):
            return existing, False

        importacao = existing or CaepiImportacao(
            sha256=digest,
            tamanho_bytes=tamanho_bytes,
            criado_por=user,
        )
        if importacao.arquivo_fonte:
            importacao.arquivo_fonte.delete(save=False)
        importacao.registros.all().delete() if importacao.pk else None
        importacao.nome_arquivo = nome[:255]
        importacao.tamanho_bytes = tamanho_bytes
        importacao.criado_por = user
        importacao.status = CaepiImportacao.Status.PROCESSANDO
        importacao.erro = ''
        importacao.advertencias = []
        importacao.total_registros = 0
        importacao.processados = 0
        importacao.novos = 0
        importacao.alterados = 0
        importacao.inalterados = 0
        importacao.rejeitados = 0
        importacao.finalizado_em = None
        importacao.publicado_em = None
        uploaded_file.seek(0)
        importacao.arquivo_fonte.save(nome, uploaded_file, save=False)
        importacao.save()
        return importacao, True

    @classmethod
    def processar_upload_salvo(cls, importacao_id):
        """Compatibilidade para jobs: conclui a fonte usando lotes retomáveis."""
        while True:
            importacao = cls.processar_lote_salvo(
                importacao_id,
                max_rows=cls.WEB_BATCH_ROWS,
                max_seconds=cls.WEB_BATCH_SECONDS,
            )
            if importacao.status != CaepiImportacao.Status.PROCESSANDO:
                return importacao

    @classmethod
    def processar_lote_salvo(
        cls, importacao_id, *, max_rows=None, max_seconds=None,
    ):
        """Processa um lote curto e retoma pela quantidade de linhas consumidas.

        A linha do arquivo é o cursor persistente. O lock impede que duas abas
        avancem o mesmo cursor; ``ignore_conflicts`` mantém a carga idempotente.
        """
        max_rows = max(1, int(max_rows or cls.WEB_BATCH_ROWS))
        max_seconds = max(1, int(max_seconds or cls.WEB_BATCH_SECONDS))
        started = time.monotonic()
        try:
            with transaction.atomic():
                importacao = (
                    CaepiImportacao.objects.select_for_update()
                    .select_related('criado_por')
                    .get(pk=importacao_id)
                )
                if importacao.status in {
                    CaepiImportacao.Status.PREVIA,
                    CaepiImportacao.Status.PUBLICADA,
                    CaepiImportacao.Status.SUBSTITUIDA,
                }:
                    return importacao
                if importacao.status == CaepiImportacao.Status.FALHOU:
                    raise ValidationError(
                        'A importação falhou por conteúdo inválido; reenvie o arquivo.'
                    )
                if not importacao.arquivo_fonte:
                    raise ValidationError(
                        'O arquivo-fonte da importação não foi encontrado.'
                    )

                importacao.status = CaepiImportacao.Status.PROCESSANDO
                importacao.erro = ''
                importacao.finalizado_em = None
                registros = []
                rejeitados_lote = 0
                consumidos = 0
                fim_arquivo = False
                advertencias = list(importacao.advertencias or [])

                with importacao.arquivo_fonte.open('rb') as source:
                    with cls._content_stream(source) as content_stream:
                        linhas = iter(cls._rows(cls._text_stream(content_stream)))
                        for _ in range(int(importacao.processados)):
                            try:
                                next(linhas)
                            except StopIteration:
                                fim_arquivo = True
                                break

                        batch_started = time.monotonic()
                        while not fim_arquivo and consumidos < max_rows:
                            if time.monotonic() - batch_started >= max_seconds:
                                break
                            try:
                                dados, advertencia = next(linhas)
                            except StopIteration:
                                fim_arquivo = True
                                break
                            consumidos += 1
                            if advertencia:
                                rejeitados_lote += 1
                                if len(advertencias) < 100:
                                    advertencias.append(advertencia)
                            else:
                                registros.append(CaepiRegistro(
                                    importacao=importacao,
                                    **dados,
                                ))

                if registros:
                    CaepiRegistro.objects.bulk_create(
                        registros,
                        batch_size=cls.INSERT_BATCH_SIZE,
                        ignore_conflicts=True,
                    )
                importacao.processados += consumidos
                importacao.rejeitados += rejeitados_lote
                importacao.advertencias = advertencias
                importacao.duracao_ms += int((time.monotonic() - started) * 1000)

                if fim_arquivo:
                    cls._finalizar_previa_em_lote(importacao)
                importacao.save()
                return importacao
        except Exception as exc:
            logger.exception(
                'Falha ao processar lote da importação CAEPI %s.', importacao_id,
            )
            if not isinstance(exc, ValidationError) or 'falhou por conteúdo' not in str(exc):
                status_falha = (
                    CaepiImportacao.Status.FALHOU
                    if isinstance(exc, ValidationError)
                    else CaepiImportacao.Status.INTERROMPIDA
                )
                CaepiImportacao.objects.filter(pk=importacao_id).exclude(
                    status__in=[
                        CaepiImportacao.Status.PREVIA,
                        CaepiImportacao.Status.PUBLICADA,
                        CaepiImportacao.Status.SUBSTITUIDA,
                    ],
                ).update(
                    status=status_falha,
                    erro=str(exc),
                    finalizado_em=timezone.now(),
                    atualizado_em=timezone.now(),
                )
            raise

    @classmethod
    def _finalizar_previa_em_lote(cls, importacao):
        publicada = CaepiImportacao.objects.filter(
            status=CaepiImportacao.Status.PUBLICADA,
        ).exclude(pk=importacao.pk).first()
        total_registros = importacao.registros.count()
        hashes_recebidos = importacao.registros.values('hash_registro')
        if publicada:
            inalterados = publicada.registros.filter(
                hash_registro__in=Subquery(hashes_recebidos),
            ).count()
            alterados = publicada.registros.exclude(
                hash_registro__in=Subquery(hashes_recebidos),
            ).count()
        else:
            inalterados = 0
            alterados = 0
        linhas_validas = int(importacao.processados) - int(importacao.rejeitados)
        duplicadas = linhas_validas - total_registros
        advertencias = list(importacao.advertencias or [])
        if duplicadas and len(advertencias) < 100:
            advertencias.append(
                f'{duplicadas} linha(s) exatamente duplicada(s) foram '
                'consolidadas sem perda de informação.'
            )
        importacao.total_registros = total_registros
        importacao.novos = total_registros - inalterados
        importacao.alterados = alterados
        importacao.inalterados = inalterados
        importacao.advertencias = advertencias
        importacao.status = CaepiImportacao.Status.PREVIA
        importacao.finalizado_em = timezone.now()

    @classmethod
    def _fingerprint(cls, uploaded_file):
        uploaded_file.seek(0)
        digest = hashlib.sha256()
        total = 0
        while True:
            chunk = uploaded_file.read(cls.HASH_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > cls.MAX_UPLOAD_BYTES:
                raise ValidationError('O arquivo excede o limite de 150 MB.')
            digest.update(chunk)
        uploaded_file.seek(0)
        return digest.hexdigest(), total

    @classmethod
    @contextmanager
    def _content_stream(cls, uploaded_file):
        uploaded_file.seek(0)
        signature = uploaded_file.read(4)
        uploaded_file.seek(0)
        archive = None
        source = uploaded_file
        try:
            if signature.startswith(b'PK\x03\x04'):
                try:
                    archive = zipfile.ZipFile(uploaded_file)
                except zipfile.BadZipFile as exc:
                    raise ValidationError('Arquivo ZIP inválido.') from exc
                files = [item for item in archive.infolist() if not item.is_dir()]
                if len(files) != 1:
                    raise ValidationError('O ZIP deve conter exatamente um CSV ou TXT.')
                item = files[0]
                if item.file_size > cls.MAX_EXTRACTED_BYTES:
                    raise ValidationError('O conteúdo descompactado excede 350 MB.')
                if '..' in item.filename.replace('\\', '/').split('/'):
                    raise ValidationError('O ZIP contém um caminho inválido.')
                source = archive.open(item)
            elif signature.startswith(b'\x1f\x8b'):
                source = _GzipStream(uploaded_file, cls.HASH_CHUNK_BYTES)

            buffered = io.BufferedReader(
                _LimitedReader(source, cls.MAX_EXTRACTED_BYTES),
                buffer_size=cls.HASH_CHUNK_BYTES,
            )
            try:
                yield buffered
            finally:
                buffered.close()
        except (gzip.BadGzipFile, EOFError) as exc:
            raise ValidationError('Arquivo GZIP inválido.') from exc
        finally:
            if archive is not None:
                archive.close()

    @staticmethod
    def _text_stream(content_stream):
        sample = content_stream.peek(64 * 1024)[:64 * 1024]
        try:
            sample.decode('utf-8-sig')
            encoding = 'utf-8-sig'
        except UnicodeDecodeError:
            encoding = 'cp1252'
        return io.TextIOWrapper(content_stream, encoding=encoding, newline='')

    @staticmethod
    def _parse_date(value):
        value = (value or '').strip()
        if not value:
            return None
        try:
            return datetime.strptime(value, '%d/%m/%Y').date()
        except ValueError as exc:
            raise ValidationError(f'Data de validade inválida: {value}.') from exc

    @classmethod
    def _rows(cls, text_stream):
        reader = csv.DictReader(text_stream, delimiter=';')
        if not reader.fieldnames:
            raise ValidationError('O arquivo não possui cabeçalho.')
        reader.fieldnames = [name.lstrip('\ufeff').strip() for name in reader.fieldnames]
        missing = sorted(cls.REQUIRED_COLUMNS - set(reader.fieldnames))
        if missing:
            raise ValidationError('Colunas obrigatórias ausentes: ' + ', '.join(missing))
        for line_number, row in enumerate(reader, start=2):
            normalized = {
                (key or '').lstrip('\ufeff').strip(): (value or '').strip()
                for key, value in row.items()
            }
            numero_ca = normalized.get('NR Registro CA', '')
            if not numero_ca:
                yield None, f'Linha {line_number}: CA vazio.'
                continue
            try:
                validade = cls._parse_date(normalized.get('DATA DE VALIDADE'))
            except ValidationError as exc:
                yield None, f'Linha {line_number}: {exc.message}'
                continue
            data = {
                'numero_ca': numero_ca.upper(),
                'validade_ca': validade,
                'situacao': normalized.get('SITUACAO', ''),
            }
            for source, target in cls.RETAINED_MAPPING.items():
                data[target] = normalized.get(source, '')
            canonical = '\x1f'.join(
                '' if value is None else (
                    value.isoformat() if hasattr(value, 'isoformat') else str(value)
                )
                for value in data.values()
            )
            data['hash_registro'] = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
            yield data, None

    @classmethod
    def preparar_previa(cls, *, uploaded_file, user):
        started = time.monotonic()
        digest, tamanho_bytes = cls._fingerprint(uploaded_file)
        existing = CaepiImportacao.objects.filter(sha256=digest).first()
        if existing and existing.status == CaepiImportacao.Status.PROCESSANDO:
            if existing.atualizado_em > timezone.now() - cls.STALE_AFTER:
                return existing
            existing.status = CaepiImportacao.Status.INTERROMPIDA
            existing.erro = (
                'A execução anterior foi interrompida antes da conclusão. '
                'O mesmo arquivo poderá ser processado novamente.'
            )
            existing.finalizado_em = timezone.now()
            existing.save(update_fields=(
                'status', 'erro', 'finalizado_em', 'atualizado_em',
            ))
        if existing and existing.status not in (
            CaepiImportacao.Status.FALHOU,
            CaepiImportacao.Status.INTERROMPIDA,
        ):
            return existing
        if existing:
            importacao = existing
            importacao.registros.all().delete()
            importacao.status = CaepiImportacao.Status.PROCESSANDO
            importacao.erro = ''
            importacao.advertencias = []
            importacao.total_registros = 0
            importacao.novos = 0
            importacao.alterados = 0
            importacao.inalterados = 0
            importacao.rejeitados = 0
            importacao.processados = 0
            importacao.criado_por = user
            importacao.finalizado_em = None
            importacao.publicado_em = None
            importacao.nome_arquivo = (uploaded_file.name or 'caepi.csv')[:255]
            importacao.tamanho_bytes = tamanho_bytes
            importacao.save()
        else:
            importacao = CaepiImportacao.objects.create(
                nome_arquivo=(uploaded_file.name or 'caepi.csv')[:255],
                sha256=digest,
                tamanho_bytes=tamanho_bytes,
                criado_por=user,
            )
        try:
            records = []
            rejected = 0
            valid_source_rows = 0
            warnings = []
            with cls._content_stream(uploaded_file) as content_stream:
                text_stream = cls._text_stream(content_stream)
                for data, warning in cls._rows(text_stream):
                    if warning:
                        rejected += 1
                        if len(warnings) < 100:
                            warnings.append(warning)
                    else:
                        valid_source_rows += 1
                        records.append(CaepiRegistro(importacao=importacao, **data))
                    if len(records) < cls.INSERT_BATCH_SIZE:
                        continue
                    CaepiRegistro.objects.bulk_create(
                        records,
                        batch_size=cls.INSERT_BATCH_SIZE,
                        ignore_conflicts=True,
                    )
                    records = []
                    CaepiImportacao.objects.filter(pk=importacao.pk).update(
                        processados=valid_source_rows + rejected,
                        rejeitados=rejected,
                        atualizado_em=timezone.now(),
                    )
            if records:
                CaepiRegistro.objects.bulk_create(
                    records,
                    batch_size=cls.INSERT_BATCH_SIZE,
                    ignore_conflicts=True,
                )

            published = CaepiImportacao.objects.filter(
                status=CaepiImportacao.Status.PUBLICADA,
            ).exclude(pk=importacao.pk).first()
            total_registros = importacao.registros.count()
            incoming_hashes = importacao.registros.values('hash_registro')
            if published:
                inalterados = published.registros.filter(
                    hash_registro__in=Subquery(incoming_hashes),
                ).count()
                alterados = published.registros.exclude(
                    hash_registro__in=Subquery(incoming_hashes),
                ).count()
            else:
                inalterados = 0
                alterados = 0
            duplicate_rows = valid_source_rows - total_registros
            if duplicate_rows:
                warnings.append(
                    f'{duplicate_rows} linha(s) exatamente duplicada(s) foram '
                    'consolidadas sem perda de informação.'
                )
            importacao.total_registros = total_registros
            importacao.processados = valid_source_rows + rejected
            importacao.novos = total_registros - inalterados
            importacao.alterados = alterados
            importacao.inalterados = inalterados
            importacao.rejeitados = rejected
            importacao.advertencias = warnings
            importacao.status = CaepiImportacao.Status.PREVIA
            importacao.finalizado_em = timezone.now()
            importacao.duracao_ms = int((time.monotonic() - started) * 1000)
            importacao.save()
            return importacao
        except Exception as exc:
            importacao.status = CaepiImportacao.Status.FALHOU
            importacao.erro = str(exc)
            importacao.finalizado_em = timezone.now()
            importacao.duracao_ms = int((time.monotonic() - started) * 1000)
            importacao.save(update_fields=(
                'status', 'erro', 'finalizado_em', 'duracao_ms',
            ))
            raise

    @classmethod
    @transaction.atomic
    def publicar(cls, importacao_id):
        importacao = CaepiImportacao.objects.select_for_update().get(pk=importacao_id)
        if importacao.status == CaepiImportacao.Status.PUBLICADA:
            return importacao
        if importacao.status != CaepiImportacao.Status.PREVIA:
            raise ValidationError('Somente uma prévia concluída pode ser publicada.')
        anteriores = CaepiImportacao.objects.select_for_update().filter(
            status=CaepiImportacao.Status.PUBLICADA,
        )
        anteriores.update(status=CaepiImportacao.Status.SUBSTITUIDA)
        importacao.status = CaepiImportacao.Status.PUBLICADA
        importacao.publicado_em = timezone.now()
        importacao.save(update_fields=('status', 'publicado_em'))
        return importacao
