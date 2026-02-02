from django.core.management.base import BaseCommand
from inventario.models import Insumo, MovimientoStock, Prestamo

class Command(BaseCommand):
    help = 'Limpia movimientos y préstamos para reiniciar el stock a 0 (Mantiene los productos)'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("⚠️  ATENCIÓN: Esto borrará TODOS los movimientos y préstamos de prueba."))
        self.stdout.write(self.style.WARNING("   Los productos (Insumos) que creaste NO se borrarán, pero su stock quedará en 0."))
        
        confirm = input("¿Estás seguro de que querés resetear el inventario a cero? (s/n): ")

        if confirm.lower() == 's':
            self.stdout.write("🧹 Iniciando limpieza...")
            
            # 1. Borrar movimientos y préstamos
            del_movs, _ = MovimientoStock.objects.all().delete()
            del_pres, _ = Prestamo.objects.all().delete()
            
            self.stdout.write(f"   - {del_movs} movimientos eliminados.")
            self.stdout.write(f"   - {del_pres} préstamos eliminados.")

            # 2. Resetear stock de insumos
            count = Insumo.objects.all().update(stock_actual=0)
            self.stdout.write(f"   - {count} productos reseteados a stock 0.")

            self.stdout.write(self.style.SUCCESS("✅ ¡Listo! El inventario está limpio."))
            self.stdout.write(self.style.SUCCESS("👉 Ahora podés ir a 'Registrar Movimiento' > 'Entrada' para hacer la carga inicial real."))
        else:
            self.stdout.write(self.style.ERROR("Operación cancelada."))