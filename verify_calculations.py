import sys
from rbwr_overlay import Calculator

def run_tests() -> bool:
    print("==================================================")
    print("      RBWR OVERLAY CALCULATION VERIFICATION")
    print("==================================================")
    
    all_tests_passed = True
    calc = Calculator(usage=61.32)
    
    print("\n[TEST 1] Testing Unit 1 Bidirectional Conversion:")
    calc.selected_unit = 1
    
    demands_to_test = [0.0, 100.0, 500.0, 1000.0, 1500.0]
    all_passed_u1 = True
    
    for d in demands_to_test:
        thermal = calc.calc_thermal(d)
        gen_load = calc.calc_gen_load(thermal)
        flow = calc.calc_flow(thermal)
        recalculated_demand = max(0.0, round(gen_load - calc.usage, 2))
        
        print(f"  Input Demand: {d:>6.1f} MWe | RTP: {thermal:>6.2f}% | Flow: {flow:>8.2f} kg/s | Recalc Demand: {recalculated_demand:>6.1f} MWe")
        
        if abs(d - recalculated_demand) > 0.05 and d > 0:
            print(f"    [FAIL] Deviation detected for Demand {d}! Recalc={recalculated_demand}")
            all_passed_u1 = False
            
    if all_passed_u1:
        print("  [OK] Unit 1 conversion checks passed successfully!")
    else:
        print("  [FAIL] Unit 1 conversion checks failed!")
        all_tests_passed = False

    print("\n[TEST 2] Testing Unit 2 Bidirectional Conversion:")
    calc.selected_unit = 2
    
    demands_to_test = [0.0, 100.0, 500.0, 1000.0, 1500.0]
    all_passed_u2 = True
    
    for d in demands_to_test:
        thermal = calc.calc_thermal(d)
        gen_load = calc.calc_gen_load(thermal)
        flow = calc.calc_flow(thermal)
        recalculated_demand = max(0.0, round(gen_load - calc.usage, 2))
        
        print(f"  Input Demand: {d:>6.1f} MWe | RTP: {thermal:>6.2f}% | Flow: {flow:>8.2f} kg/s | Recalc Demand: {recalculated_demand:>6.1f} MWe")
        
        if abs(d - recalculated_demand) > 2.0 and d > 0:
            print(f"    [FAIL] Deviation detected for Demand {d}! Recalc={recalculated_demand}")
            all_passed_u2 = False

    if all_passed_u2:
        print("  [OK] Unit 2 conversion checks passed successfully!")
    else:
        print("  [FAIL] Unit 2 conversion checks failed!")
        all_tests_passed = False

    print("\n[TEST 3] Dynamic Usage Calculation Check:")
    calc.selected_unit = 1
    
    thermal_500 = calc.calc_thermal(500)
    usage_500 = calc.usage
    print(f"  Unit 1 (Demand = 500)  | RTP: {thermal_500:>6.2f}% | Dynamic Usage: {usage_500:>6.2f} MWe")
    
    thermal_1000 = calc.calc_thermal(1000)
    usage_1000 = calc.usage
    print(f"  Unit 1 (Demand = 1000) | RTP: {thermal_1000:>6.2f}% | Dynamic Usage: {usage_1000:>6.2f} MWe")
    
    if usage_1000 > usage_500:
        print("  [OK] Dynamic usage successfully increases with demand load!")
    else:
        print("  [FAIL] Dynamic usage calculation error!")
        all_tests_passed = False

    print("\n[TEST 4] Recirculation Override Check:")
    calc.selected_unit = 1
    calc.recirc_override = None
    thermal_default = calc.calc_thermal(1000)
    
    calc.recirc_override = 60.0
    thermal_override = calc.calc_thermal(1000)
    calc.recirc_override = None
    
    print(f"  Unit 1 (Demand = 1000) | Normal RTP: {thermal_default:>6.2f}% | Recirc Override (60%) RTP: {thermal_override:>6.2f}%")
    if thermal_override > 0:
        print("  [OK] Recirculation override calculated successfully!")
    else:
        print("  [FAIL] Recirculation override calculation failed!")
        all_tests_passed = False

    print("\n==================================================")
    if all_tests_passed:
        print("         ALL CALCULATION CHECKS PASSED [OK]")
    else:
        print("        SOME CALCULATION CHECKS FAILED [FAIL]")
    print("==================================================")
    
    return all_tests_passed

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)