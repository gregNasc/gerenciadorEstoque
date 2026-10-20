import csv
import hashlib
import io
import time
import zipfile
import zlib
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from integracao.models import CaepiImportacao, CaepiRegistro


class CaepiImportService:
    MAX_UPLOAD_BYTES = 150 * 1024 * 1024
    MAX_EXTRACTED_BYTES = 350 * 1024 * 1024
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
    def _extract(cls, payload):
        if len(payload) > cls.MAX_UPLOAD_BYTES:
            raise ValidationError('O arquivo excede o limite de 80 MB.')
        if payload.startswith(b'PK\x03\x04'):
            try:
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    files = [item for item in archive.infolist() if not item.is_dir()]
                    if len(files) != 1:
                        raise ValidationError('O ZIP deve conter exatamente um CSV ou TXT.')
                    item = files[0]
                    if item.file_size > cls.MAX_EXTRACTED_BYTES:
                        raise ValidationError('O conteúdo descompactado excede 350 MB.')
                    if '..' in item.filename.replace('\\', '/').split('/'):
                        raise ValidationError('O ZIP contém um caminho inválido.')
                    return archive.read(item)
            except zipfile.BadZipFile as exc:
                raise ValidationError('Arquivo ZIP inválido.') from exc
        if payload.startswith(b'\x1f\x8b'):
            try:
                decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
                content = decoder.decompress(payload, cls.MAX_EXTRACTED_BYTES + 1)
                content += decoder.flush()
            except zlib.error as exc:
                raise ValidationError('Arquivo GZIP inválido.') from exc
            if len(content) > cls.MAX_EXTRACTED_BYTES:
                raise ValidationError('O conteúdo descompactado excede 350 MB.')
            return content
        if len(payload) > cls.MAX_EXTRACTED_BYTES:
            raise ValidationError('O conteúdo excede 350 MB.')
        return payload

    @staticmethod
    def _decode(content):
        for encoding in ('utf-8-sig', 'cp1252'):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValidationError('Codificação não reconhecida; use UTF-8 ou Windows-1252.')

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
    def _rows(cls, content):
        text = cls._decode(content)
        reader = csv.DictReader(io.StringIO(text, newline=''), delimiter=';')
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
        payload = uploaded_file.read(cls.MAX_UPLOAD_BYTES + 1)
        if len(payload) > cls.MAX_UPLOAD_BYTES:
            raise ValidationError('O arquivo excede o limite de 80 MB.')
        digest = hashlib.sha256(payload).hexdigest()
        existing = CaepiImportacao.objects.filter(sha256=digest).first()
        if existing and existing.status != CaepiImportacao.Status.FALHOU:
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
            importacao.criado_por = user
            importacao.save()
        else:
            importacao = CaepiImportacao.objects.create(
                nome_arquivo=(uploaded_file.name or 'caepi.csv')[:255],
                sha256=digest,
                tamanho_bytes=len(payload),
                criado_por=user,
            )
        try:
            content = cls._extract(payload)
            records = []
            rejected = 0
            valid_source_rows = 0
            warnings = []
            for data, warning in cls._rows(content):
                if warning:
                    rejected += 1
                    if len(warnings) < 100:
                        warnings.append(warning)
                    continue
                valid_source_rows += 1
                records.append(CaepiRegistro(importacao=importacao, **data))
                if len(records) >= 2000:
                    CaepiRegistro.objects.bulk_create(
                        records, batch_size=2000, ignore_conflicts=True,
                    )
                    records = []
            if records:
                CaepiRegistro.objects.bulk_create(
                    records, batch_size=2000, ignore_conflicts=True,
                )

            published = CaepiImportacao.objects.filter(
                status=CaepiImportacao.Status.PUBLICADA,
            ).first()
            current_hashes = set(
                published.registros.values_list('hash_registro', flat=True)
            ) if published else set()
            incoming_hashes = set(
                importacao.registros.values_list('hash_registro', flat=True)
            )
            duplicate_rows = valid_source_rows - len(incoming_hashes)
            if duplicate_rows:
                warnings.append(
                    f'{duplicate_rows} linha(s) exatamente duplicada(s) foram '
                    'consolidadas sem perda de informação.'
                )
            unchanged = len(current_hashes & incoming_hashes)
            importacao.total_registros = len(incoming_hashes)
            importacao.novos = len(incoming_hashes - current_hashes)
            importacao.alterados = max(0, len(current_hashes - incoming_hashes))
            importacao.inalterados = unchanged
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
