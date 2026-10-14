from backend.converter import convert_locally


def test_sum_without_table_preserves_field():
    result = convert_locally("SUM([Sales])")
    assert result.dax == "SUM([Sales])"
    assert result.needs_ai is False
    assert any("No table name" in warning for warning in result.warnings)


def test_avg_and_table_qualification():
    result = convert_locally("AVG([Net Sales])", "Sales_Data")
    assert result.dax == "AVERAGE('Sales_Data'[Net Sales])"
    assert result.needs_ai is False


def test_simple_if_then_else():
    result = convert_locally("IF [Sales] > 100 THEN [Sales] ELSE 0 END", "Sales_Data")
    assert result.dax == "IF('Sales_Data'[Sales] > 100, 'Sales_Data'[Sales], 0)"


def test_lod_routes_to_ai():
    result = convert_locally("{ FIXED [Customer ID] : SUM([Sales]) }")
    assert result.needs_ai is True
